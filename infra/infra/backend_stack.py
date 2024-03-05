# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0


from pathlib import Path
import subprocess

from aws_cdk import (
    Aspects, CfnOutput, Duration, Fn, Stack, )
from aws_cdk.aws_ec2 import Vpc, SubnetType, SubnetSelection, Port, Subnet, CfnSecurityGroupIngress
from aws_cdk.aws_lambda import LayerVersion, Code, Runtime, Function
from constructs import Construct
from cdk_nag import AwsSolutionsChecks, NagSuppressions

from infra.cluster_sizing import ClusterConfig
from infra.opensearch_rp import OpensearchRp
from infra.opensearch import Opensearch
from infra.opensearch_bootstrap import OpensearchBootstrap
from infra.opensearch_cr_helpers import OpensearchCrHelpers
from infra.opensearch_prereq import OpensearchPreReq
from infra.opensearch_secret import OpensearchSecret
from infra.opensearch_rp_cr import OpensearchRpCr


class BackendStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Stack, needed to get region and account ID
        stack = Stack.of(self)

        # Parameter for T-shirt sizing the Opensearch domain
        self.__tshirt_size = ClusterConfig.load_tshirt_size(self.node.try_get_context("TshirtSize"))
        cluster_sizing = ClusterConfig(self.__tshirt_size)

        # Get the VPC from parameter or create a new one
        vpc_id_param = scope.node.try_get_context("VpcID")
        if vpc_id_param is None:
            vpc = Vpc(self, 'Vpc', max_azs=3)
        else:
            vpc = Vpc.from_lookup(self, 'Vpc', vpc_id=vpc_id_param)

        # Get the AZ count from the configuration or 1 for XS size
        try:
            az_count = cluster_sizing.cluster_config.zone_awareness_config.availability_zone_count
        except:
            az_count = 1

        # Get the Subnets for Opensearch domain from parameters or takes private ones from the Vpc with one per AZ.
        # List of subnet is capped to the number of AZ required by the Opensearch Domain
        os_subnets_ids_param = scope.node.try_get_context("OpensearchSubnetsIDs")
        if os_subnets_ids_param is None:
            os_subnets = SubnetSelection(
                subnets=vpc.select_subnets(one_per_az=True, subnet_type=SubnetType.PRIVATE_WITH_EGRESS).subnets[
                        :az_count])
        else:
            os_subnets = SubnetSelection(subnets=list(map(lambda s: Subnet.from_subnet_id(self, s, subnet_id=s), os_subnets_ids_param.split(',', az_count))))

        # Get the Public Subnet for the Reverse Proxy from parameters or takes a public one from the VPC.
        rp_subnet_id_param = scope.node.try_get_context("ReverseProxySubnetID")
        if rp_subnet_id_param is None:
            rp_subnet = SubnetSelection(
                subnets=vpc.select_subnets(subnet_type=SubnetType.PUBLIC).subnets[:1])
        else:
            rp_subnet = SubnetSelection(subnets=[Subnet.from_subnet_id(self, 'RpSubnet', subnet_id=rp_subnet_id_param)])

        # Initialize resources for the Opensearch domain
        prereq = OpensearchPreReq(self, 'PreReq', vpc, os_subnets)

        # The name of the lambda function for the custom resource
        bootstrap_function_name = 'opensearch-custom-resource'
        rotation_function_name='opensearch-rotation'
        bootstrap_cr_helpers = OpensearchCrHelpers(self, 'BoostrapCrHelpers', bootstrap_function_name, prereq)
        secret_cr_helpers = OpensearchCrHelpers(self, 'SecretCrHelpers', rotation_function_name, prereq)
        
        # Build the lambda layer assets
        subprocess.call(
            ['pip', 'install', '-t',
             Path(__file__).parent.joinpath('./resources/lambda/layer/python/lib/python3.11/site-packages'), '-r',
             Path(__file__).parent.joinpath('./resources/lambda/opensearch-bootstrap/requirements.txt'), '--upgrade'])

        requirements_layer = LayerVersion(scope=self,
                                          id='PythonRequirementsTemplate',
                                          code=Code.from_asset(
                                              str(Path(__file__).parent.joinpath('resources/lambda/layer'))),
                                          compatible_runtimes=[Runtime.PYTHON_3_11])
        
                
        rotate_function = Function(self, 'RotateFunction',
                                                   function_name=secret_cr_helpers.function_name,
                                                   code=Code.from_asset(str(Path(__file__).parent.joinpath('resources/lambda/opensearch-rotation'))),
                                                   handler='rotate.lambda_handler',
                                                   runtime=Runtime.PYTHON_3_11,
                                                   layers=[requirements_layer],
                                                   timeout=Duration.seconds(120),
                                                   environment={
                                                       'DOMAIN_NAME': secret_cr_helpers.domain_name,
                                                   },
                                                   role=secret_cr_helpers.role,
                                                   vpc=secret_cr_helpers.vpc,
                                                   vpc_subnets=secret_cr_helpers.subnets,
                                                   security_groups=[secret_cr_helpers.security_group],
                                                   )
        
        # Opensearch dashboard user secret
        user_secret = OpensearchSecret(self, 'UserSecret', 'user', secret_cr_helpers, rotate_function)

        # Opensearch dashboard admin secret
        admin_secret = OpensearchSecret(self, 'AdminSecret', 'admin', secret_cr_helpers, rotate_function)

        domain = Opensearch(self, 'Domain', prereq, bootstrap_cr_helpers.role, cluster_sizing)
        
        # Authorize inbound HTTPS traffic on port 443
        # prereq.domain_security_group.add_ingress_rule(
        #     peer=bootstrap_cr_helpers.security_group,
        #     connection=Port.tcp(443),
        # )

        # We use Cfn resource to get an object and add dependency on the custom resource
        from_cr_ingress = CfnSecurityGroupIngress(self, 'CrToDomainIngress', 
                                                  ip_protocol='TCP',
                                                  to_port=443,
                                                  source_security_group_id=bootstrap_cr_helpers.security_group.security_group_id
                                                  )

        cr = OpensearchBootstrap(self, 'OsBootstrap', bootstrap_cr_helpers, domain.domain, requirements_layer, user_secret.secret, admin_secret.secret, domain.pipeline_role)
        # We add dependency to avoid race condition on ingress rule deletion
        cr.node.add_dependency(from_cr_ingress)

        rp = OpensearchRp(self, 'ReverseProxy', domain.domain, vpc, rp_subnet)

        prereq.domain_security_group.add_ingress_rule(
            peer=rp.security_group,
            connection=Port.tcp(443),
        )

        rp_custom_resource = OpensearchRpCr(self, 'RpCustomResource', rp.autoscaling_group)
        
        CfnOutput(self, 'OpensearchDashboardUrl',
                  description='Opensearch Dashboard URL',
                  value=Fn.join("", [
                      "https://",
                      rp_custom_resource.custom_resource.get_att_string('PublicIpAddress'),
                      "/_dashboards"
                  ]))

        CfnOutput(self, 'OpensearchDomainEndpoint',
                  description='Opensearch Dashboard URL',
                  value=domain.domain.get_att('DomainEndpoint').to_string()
                  )
        self.opensearch_domain_endpoint = domain.domain.get_att('DomainEndpoint').to_string()

        CfnOutput(self, 'PipelineRoleArn',
                  description='Role ARN to use by the Opensearch Ingestion pipeline',
                  value=domain.pipeline_role.role_arn
                  )
        self.pipeline_role_arn = domain.pipeline_role.role_arn

        CfnOutput(self, 'OpensearchIndexes',
                  description='Indexes used in Opensearch to store logs and metrics',
                  value='spark-logs, spark-metrics'
                  )
        Aspects.of(self).add(AwsSolutionsChecks())

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/PreReq/Role/DefaultPolicy/Resource', suppressions=[
            {"id": "AwsSolutions-IAM5", "reason": "wildcards inherited from CDK grant_write method on CloudWatch log group"},
        ])

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/BoostrapCrHelpers/LogsManagedPolicy/Resource', suppressions=[
            {"id": "AwsSolutions-IAM5", "reason": "The CloudWatch Log Stream ID is determined when it's created"},
        ])

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/ReverseProxy/SsmPolicy/Resource', suppressions=[
            {"id": "AwsSolutions-IAM5", "reason": "Wildcards are required for SSM policy"},
        ])


        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/SecretCrHelpers/LogsManagedPolicy/Resource', suppressions=[
            {"id": "AwsSolutions-IAM5", "reason": "The CloudWatch Log Stream ID is determined when it's created"},
        ])

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/RpCustomResource/LambdaRole/Resource', suppressions=[
            {"id": "AwsSolutions-IAM5", "reason": "ec2:Describe* and ec2:List* is required to find the EIP"},
            {"id": "AwsSolutions-IAM5", "reason": "Wildcard is required on resources because the CR needs to find the right EIP from existing ones"},
            {"id": "AwsSolutions-IAM5", "reason": "The log stream ID is not predictable and generated during execution time by the custom resource"}
        ])

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/Domain/PipelinePolicy/Resource', suppressions=[
            {"id": "AwsSolutions-IAM5", "reason": "The policy required by Opensearch Ingestion Pipeline needs DescribeDomain on all domains and ESHttp*"},
            {"id": "AwsSolutions-IAM5", "reason": "The policy required access to all the indexes in the Opensearch domain"}
        ])

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/Domain/SparkObservabilityDomain', suppressions=[
            {"id": "AwsSolutions-OS3", "reason": "We are using FGAC to restrict access to the domain. FGAC is enabled via a custom resource"},
            {"id": "AwsSolutions-OS4", "reason": "XS tshirtsize is for development domains without dedicated master nodes, larger domains are using dedicated master nodes"},
            {"id": "AwsSolutions-OS5", "reason": "Fine grained access control is enabled after creation of the domain via a custom resource"},
            {"id": "AwsSolutions-OS7", "reason": "XS tshirtsize is for development domains without zone awareness, larger domains are using zone awareness"},
        ])

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/OsBootstrap/BootstrapLambdaProvider/framework-onEvent', suppressions=[
            {"id": "AwsSolutions-IAM4", "reason": "The custom resource provider framework cannot be customized and use an AWS managed policy"},
            {"id": "AwsSolutions-IAM5", "reason": "The custom resource provider framework cannot be customized and use wildcards in its policy"},
            {"id": "AwsSolutions-L1", "reason": "The lambda from CDK custom resource provider framework cannot be configured"},
        ],
        apply_to_children=True,
        )

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/ReverseProxy/RpSecurityGroup/Resource', suppressions=[
            {"id": "AwsSolutions-EC23", "reason": "The security group needs to allow 0.0.0.0/0 or ::/0 for accessing dashboards outside of private subnets"},
        ])
        
        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/RpCustomResource/GetEC2PublicIP/Resource', suppressions=[
            {"id": "AwsSolutions-L1", "reason": "Python 3.11 is the latest version"},
        ])

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/OsBootstrap/OsBootstrapFunction/Resource', suppressions=[
            {"id": "AwsSolutions-L1", "reason": "Python 3.11 is the latest version"},
        ])

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/RotateFunction/Resource', suppressions=[
            {"id": "AwsSolutions-L1", "reason": "Python 3.11 is the latest version"},
        ])

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/RpCustomResource/Provider/framework-onEvent/ServiceRole/Resource', suppressions=[
            {"id": "AwsSolutions-IAM4", "reason": "Managed policy used by the Cutom Resource Provider Framework, not configurable"},
        ])

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/RpCustomResource/Provider/framework-onEvent/ServiceRole/DefaultPolicy/Resource', suppressions=[
            {"id": "AwsSolutions-IAM5", "reason": "Not possible to know the EIP arn, it's dynamic"},
        ])

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/BackendStack/RpCustomResource/Provider/framework-onEvent/Resource', suppressions=[
            {"id": "AwsSolutions-L1", "reason": "Lambda function runtime provided by the custom resource provider framework. Not configurable"},
        ])

        NagSuppressions.add_resource_suppressions_by_path(self, '/BackendStack/LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8a/ServiceRole',[
            {"id": "AwsSolutions-IAM4", "reason": "Role configured by the Log Retention feature from Custom Resource Provider Framework. Not configurable."},
            {"id": "AwsSolutions-IAM5", "reason": "Role configured by the Log Retention feature from Custom Resource Provider Framework. Not configurable."},
        ], True)
