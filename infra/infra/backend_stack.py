# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import subprocess
from pathlib import Path

from aws_cdk import (
    Stack, RemovalPolicy, CfnOutput, CfnTag, Fn, Duration, CustomResource, )
from aws_cdk.aws_autoscaling import CfnLaunchConfiguration, CfnAutoScalingGroup
from aws_cdk.aws_ec2 import Vpc, SubnetType, SubnetSelection, SecurityGroup, Port, Peer
from aws_cdk.aws_iam import InstanceProfile, CfnServiceLinkedRole, ManagedPolicy, PolicyStatement, ServicePrincipal, \
    Role, PolicyDocument
from aws_cdk.aws_kms import Key
from aws_cdk.aws_lambda import LayerVersion, Code, Runtime, Function
from aws_cdk.aws_logs import LogGroup, RetentionDays
from aws_cdk.aws_opensearchservice import CfnDomain
from aws_cdk.aws_secretsmanager import Secret, SecretStringGenerator
from aws_cdk.custom_resources import Provider
from constructs import Construct

from infra.cluster_sizing import ClusterConfig


class BackendStack(Stack):
    amis = {
        'us-east-1': 'ami-08a52ddb321b32a8c',
        'us-east-2': 'ami-0ccabb5f82d4c9af5',
        'us-west-2': 'ami-04e35eeae7a7c5883',
        'us-west-1': 'ami-09f67f6dc966a7829',
        'eu-west-1': 'ami-0ed752ea0f62749af',
        'eu-west-2': 'ami-0f3d9639a5674d559',
        'eu-west-3': 'ami-07e67bd6b5d9fd892',
        'eu-central-1': 'ami-0c4c4bd6cf0c5fe52',
        'sa-east-1': 'ami-00a16e018e54305c6',
    }

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Stack, needed to get region and account ID
        stack = Stack.of(self)

        # master role for Opensearch domain
        # assumed by lambda because we are using a customer resource to configure the cluster via Opensearch API
        master_role = Role(self, 'MasterOpensearchRole',
                           assumed_by=ServicePrincipal('lambda.amazonaws.com'),
                           managed_policies=[
                               ManagedPolicy.from_aws_managed_policy_name(
                                   'service-role/AWSLambdaBasicExecutionRole'),
                           ])

        # add permission to update the cluster after creation. required to enable FGAC with internal database users
        master_role.add_to_policy(
            PolicyStatement(
                actions=['es:UpdateElasticsearchDomainConfig'],
                resources=['*'],
            ))
        master_role.add_to_policy(
            PolicyStatement(
                actions=[
                    'ec2:CreateNetworkInterface',
                    'ec2:DescribeNetworkInterfaces',
                    'ec2:DeleteNetworkInterface',

                ],
                resources=['*'],
            ))

        # Opensearch dashboard user secret
        user_secret = Secret(self, 'UserSecret',
                             generate_secret_string=SecretStringGenerator(
                                 secret_string_template=json.dumps({'username': 'user'}),
                                 generate_string_key='password',
                                 exclude_characters='"@\\/'
                             ))

        user_secret.grant_read(master_role)

        # Opensearch dashboard admin secret
        admin_secret = Secret(self, 'AdminSecret',
                              generate_secret_string=SecretStringGenerator(
                                  secret_string_template=json.dumps({'username': 'admin'}),
                                  generate_string_key='password',
                                  exclude_characters='"@\\/'
                              ))

        admin_secret.grant_read(master_role)

        # Parameter for T-shirt sizing the Opensearch domain
        self.__tshirt_size = ClusterConfig.load_tshirt_size(self.node.try_get_context("TshirtSize"))
        cluster_sizing = ClusterConfig(self.__tshirt_size)

        # Service Linked role for Amazon Opensearch
        try:
            slr = Role.from_role_name(self, 'OpensearchSlr', 'AWSServiceRoleForAmazonOpenSearchService')
        except:
            slr = CfnServiceLinkedRole(self, 'ServiceLinkedRole', aws_service_name='es.amazonaws.com')

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
            os_subnets = SubnetSelection(subnets_ids=os_subnets_ids_param.split(',', az_count))

        # Get the Public Subnet for the Reverse Proxy from parameters or takes a public one from the VPC.
        rp_subnet_id_param = scope.node.try_get_context("ReverseProxySubnetID")
        if rp_subnet_id_param is None:
            rp_subnet = SubnetSelection(
                subnets=vpc.select_subnets(subnet_type=SubnetType.PUBLIC).subnets[:1])
        else:
            rp_subnet = SubnetSelection(subnets_ids=[rp_subnet_id_param])

        domain_security_group = SecurityGroup(
            self, "DomainSecurityGroup",
            vpc=vpc
        )

        client_security_group = SecurityGroup(
            self, "ClientSecurityGroup",
            vpc=vpc
        )

        # Reverse Proxy Security Group
        reverse_proxy_sg = SecurityGroup(self, "RpSecurityGroup",
                                         vpc=vpc,
                                         )

        # Authorize inbound HTTPS traffic on port 443
        domain_security_group.add_ingress_rule(
            peer=client_security_group,
            connection=Port.tcp(443),
        )
        domain_security_group.add_ingress_rule(
            peer=reverse_proxy_sg,
            connection=Port.tcp(443),
        )

        # KMS key used to encrypt the data at rest in Opensearch
        key = Key(self, 'Key',
                  enable_key_rotation=True,
                  removal_policy=RemovalPolicy.DESTROY,
                  )

        master_role.add_to_policy(PolicyStatement(
            resources=[key.key_arn],
            actions=['kms:DescribeKey'],
        ))

        # Log group for the Opensearch domain
        log_group = LogGroup(self, 'OpensearchLogGroup',
                             removal_policy=RemovalPolicy.DESTROY,
                             retention=RetentionDays.ONE_WEEK,
                             log_group_name='spark-observability-logs',
                             )
        log_group.grant_write(ServicePrincipal("es.amazonaws.com"))

        domain = CfnDomain(self, "SparkObservabilityDomain",
                           access_policies={
                               "Version": "2012-10-17",
                               "Statement": [
                                   {
                                       "Effect": "Allow",
                                       "Principal": {
                                           "AWS": "*"
                                       },
                                       "Action": "es:*",
                                       "Resource": f"arn:aws:es:{stack.region}:{stack.account}:domain/spark-observability/*"
                                   }
                               ]
                           },
                           advanced_security_options=CfnDomain.AdvancedSecurityOptionsInputProperty(
                               enabled=True,
                               internal_user_database_enabled=False,
                               master_user_options=CfnDomain.MasterUserOptionsProperty(
                                   master_user_arn=master_role.role_arn,
                               )
                           ),
                           cluster_config=cluster_sizing.cluster_config,
                           domain_endpoint_options=CfnDomain.DomainEndpointOptionsProperty(
                               custom_endpoint_enabled=False,
                               enforce_https=True,
                               tls_security_policy="Policy-Min-TLS-1-2-2019-07"
                           ),
                           domain_name="spark-observability",
                           ebs_options=cluster_sizing.ebs_config,
                           encryption_at_rest_options=CfnDomain.EncryptionAtRestOptionsProperty(
                               enabled=True,
                               kms_key_id=key.key_id
                           ),
                           engine_version="OpenSearch_2.7",
                           # log_publishing_options={
                           #     "INDEX_SLOW_LOGS": CfnDomain.LogPublishingOptionProperty(
                           #         cloud_watch_logs_log_group_arn=log_group.log_group_arn,
                           #         enabled=True
                           #     ),
                           #     "SEARCH_SLOW_LOGS": CfnDomain.LogPublishingOptionProperty(
                           #         cloud_watch_logs_log_group_arn=log_group.log_group_arn,
                           #         enabled=True
                           #     ),
                           #     "AUDIT_LOGS": CfnDomain.LogPublishingOptionProperty(
                           #         cloud_watch_logs_log_group_arn=log_group.log_group_arn,
                           #         enabled=True
                           #     ),
                           #     "ES_APPLICATION_LOGS": CfnDomain.LogPublishingOptionProperty(
                           #         cloud_watch_logs_log_group_arn=log_group.log_group_arn,
                           #         enabled=True
                           #     ),
                           #     "TASK_DETAILS_LOGS": CfnDomain.LogPublishingOptionProperty(
                           #         cloud_watch_logs_log_group_arn=log_group.log_group_arn,
                           #         enabled=True
                           #     )
                           # },
                           node_to_node_encryption_options=CfnDomain.NodeToNodeEncryptionOptionsProperty(
                               enabled=True
                           ),
                           vpc_options=CfnDomain.VPCOptionsProperty(
                               subnet_ids=list(map(lambda subnet: subnet.subnet_id, os_subnets.subnets)),
                               security_group_ids=[domain_security_group.security_group_id]
                           ),
                           tags=[CfnTag(
                               key="spark-observability",
                               value="true"
                           )],
                           )

        # The role used by the Opensearch Ingestion pipeline
        pipeline_role = Role(self, 'PipelineRole',
                             assumed_by=ServicePrincipal('osis-pipelines.amazonaws.com'))

        # the policy attached to the OS ingestion pipeline
        pipeline_policy = ManagedPolicy(self, 'PipelinePolicy',
                                        statements=[
                                            PolicyStatement(
                                                resources=[f"arn:aws:es:*:{stack.account}:domain/*"],
                                                actions=["es:DescribeDomain"],
                                            ),
                                            PolicyStatement(
                                                resources=[domain.get_att('Arn').to_string() + '/*'],
                                                actions=["es:ESHttp*"],
                                                conditions={
                                                    "StringEquals": {
                                                        "aws:SourceAccount": stack.account
                                                    },
                                                    "ArnLike": {
                                                        "aws:SourceArn": f"arn:aws:osis:{stack.region}:{stack.account}:pipeline/*"
                                                    }
                                                }
                                            ),
                                        ],
                                        roles=[pipeline_role]
                                        )

        # Build the lambda layer assets
        subprocess.call(
            ['pip', 'install', '-t',
             Path(__file__).parent.joinpath('./resources/lambda/layer/python/lib/python3.9/site-packages'), '-r',
             Path(__file__).parent.joinpath('./resources/lambda/opensearch-bootstrap/requirements.txt'), '--upgrade'])

        requirements_layer = LayerVersion(scope=self,
                                          id='PythonRequirementsTemplate',
                                          code=Code.from_asset(
                                              str(Path(__file__).parent.joinpath('resources/lambda/layer'))),
                                          compatible_runtimes=[Runtime.PYTHON_3_9])

        bootstrap_lambda = Function(scope=self,
                                    id='OsBootstrapFunction',
                                    runtime=Runtime.PYTHON_3_9,
                                    code=Code.from_asset(
                                        str(Path(__file__).parent.joinpath('resources/lambda/opensearch-bootstrap'))),
                                    handler='bootstrap.on_event',
                                    environment={'PIPELINE_ROLE_ARN': pipeline_role.role_arn,
                                                 'DOMAIN_ENDPOINT': domain.get_att('DomainEndpoint').to_string(),
                                                 'DOMAIN_NAME': 'spark-observability',
                                                 'USER_SECRET_ARN': user_secret.secret_arn,
                                                 'ADMIN_SECRET_ARN': admin_secret.secret_arn,
                                                 },
                                    layers=[requirements_layer],
                                    timeout=Duration.minutes(15),
                                    role=master_role,
                                    vpc=vpc,
                                    vpc_subnets=os_subnets,
                                    security_groups=[client_security_group]
                                    )

        bootstrap_lambda_provider = Provider(scope=self,
                                             id='BootstrapLambdaProvider',
                                             on_event_handler=bootstrap_lambda
                                             )
        os_bootstrap = CustomResource(scope=self,
                                      id='ExecuteOsBootstrap',
                                      service_token=bootstrap_lambda_provider.service_token,
                                      properties={'Timeout': 900}
                                      )

        # Reverse Proxy
        # IAM Role
        rp_role = Role(self, "RpIamRole",
                       assumed_by=ServicePrincipal("ec2.amazonaws.com"),
                       managed_policies=[
                           ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEC2RoleforSSM")
                       ]
                       )

        # Instance Profile
        instance_profile = InstanceProfile(self, "RpInstanceProfile",
                                           role=rp_role
                                           )

        reverse_proxy_sg.add_ingress_rule(
            peer=Peer.ipv4("0.0.0.0/0"),
            connection=Port.tcp(443)
        )
        reverse_proxy_sg.add_egress_rule(
            peer=Peer.ipv4("0.0.0.0/0"),
            connection=Port.all_traffic()
        )

        try:
            ami = self.amis[stack.region]
        except:
            raise Exception(stack.region + " region not supported")

        # Reverse Proxy Launch Configuration
        launch_config = CfnLaunchConfiguration(self, "RpLaunchConfig",
                                               associate_public_ip_address=True,
                                               iam_instance_profile=instance_profile.instance_profile_name,
                                               image_id=ami,
                                               user_data=Fn.base64(
                                                   '''#!/bin/bash
yum update -y
yum install jq nginx -y
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/nginx/cert.key -out /etc/nginx/cert.crt -subj /C=US/ST=./L=./O=./CN=.\\n

cat << EOF > /etc/nginx/conf.d/nginx_opensearch.conf
server {{
    listen 443;
    server_name \$host;
    rewrite ^/$ https://\$host/_dashboards redirect;

    # openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/nginx/cert.key -out /etc/nginx/cert.crt -subj /C=US/ST=./L=./O=./CN=.\\n
    ssl_certificate           /etc/nginx/cert.crt;
    ssl_certificate_key       /etc/nginx/cert.key;

    ssl on;
    ssl_session_cache  builtin:1000  shared:SSL:10m;
    ssl_protocols  TLSv1 TLSv1.1 TLSv1.2;
    ssl_ciphers HIGH:!aNULL:!eNULL:!EXPORT:!CAMELLIA:!DES:!MD5:!PSK:!RC4;
    ssl_prefer_server_ciphers on;


    location ^~ /_dashboards {{
        # Forward requests to OpenSearch Dashboards
        proxy_pass https://DOMAIN_ENDPOINT/_dashboards;

        # Update cookie domain and path
        proxy_cookie_domain DOMAIN_ENDPOINT \$host;

        proxy_set_header Accept-Encoding "";
        sub_filter_types *;
        sub_filter DOMAIN_ENDPOINT \$host;
        sub_filter_once off;

        # Response buffer settings
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }}
}}          
EOF
sed -i -e "s/DOMAIN_ENDPOINT/{domain_endpoint}/g" /etc/nginx/conf.d/nginx_opensearch.conf
systemctl restart nginx.service
systemctl enable nginx.service
                                                    '''.format(
                                                       domain_endpoint=domain.get_att('DomainEndpoint').to_string()
                                                   )
                                               ),
                                               security_groups=[reverse_proxy_sg.security_group_id],
                                               instance_type='t2.micro'
                                               )

        # Reverse Proxy Auto Scaling Group
        asg = CfnAutoScalingGroup(self, "ReverseProxyASG",
                                  vpc_zone_identifier=list(map(lambda subnet: subnet.subnet_id, rp_subnet.subnets)),
                                  launch_configuration_name=launch_config.ref,
                                  min_size="1",
                                  max_size="1",
                                  tags=[
                                      CfnAutoScalingGroup.TagPropertyProperty(
                                          key="SparkObservability",
                                          value="true",
                                          propagate_at_launch=True
                                      ),
                                  ]
                                  )
        # Lambda function to retrieve the public IP of the NGINX proxy
        # IAM role for Lambda function
        lambda_role = Role(self, "LambdaRole",
                           assumed_by=ServicePrincipal("lambda.amazonaws.com"),
                           path="/",
                           inline_policies={
                               "lambda-logs": PolicyDocument(
                                   statements=[
                                       PolicyStatement(
                                           actions=[
                                               "ec2:Describe*",
                                               "ec2:List*"
                                           ],
                                           resources=["*"]
                                       ),
                                       PolicyStatement(
                                           actions=[
                                               "logs:CreateLogGroup",
                                               "logs:CreateLogStream",
                                               "logs:PutLogEvents"
                                           ],
                                           resources=["arn:aws:logs:*:*:*"]
                                       )
                                   ]
                               )
                           })

        lambda_function = Function(self, "GetEC2PublicIP",
                                   code=Code.from_inline("""
import json
import boto3
import logging
import urllib3
import time
http = urllib3.PoolManager()

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)

SUCCESS = "SUCCESS"
FAILED = "FAILED"
time.sleep(15)

def lambda_handler(event, context):
    global arn
    logger.info('Event: %s' % json.dumps(event))
    responseData={}
    try:
        if event['RequestType'] == 'Create' or event['RequestType'] == 'Update':
            print("Request Type:",event['RequestType'])
            client = boto3.client('ec2')
            PublicIpAddress = ''
            response = client.describe_instances(
                Filters=[ {
                        'Name': 'tag:SparkObservability',
                        'Values': ['true']}
                ]
            )
            for r in response['Reservations']:
                for i in r['Instances']:
                    PublicIpAddress = (i['PublicIpAddress'])
                    print (PublicIpAddress)

            responseData={'PublicIpAddress':PublicIpAddress}
            print("Sending CFN")
        responseStatus = 'SUCCESS'
    except Exception as e:
        print('Failed to process:', e)
        responseStatus = 'FAILURE'
        responseData = {'Failure': 'Check Logs.'}
    send(event, context, responseStatus, responseData)

def send(event, context, responseStatus, responseData, physicalResourceId=None, noEcho=False):
    responseUrl = event['ResponseURL']
    print(responseUrl)
    responseBody = {'Status': responseStatus,
                    'Reason': 'See the details in CloudWatch Log Stream: ' + context.log_stream_name,
                    'PhysicalResourceId': physicalResourceId or context.log_stream_name,
                    'StackId': event['StackId'],
                    'RequestId': event['RequestId'],
                    'LogicalResourceId': event['LogicalResourceId'],
                    'Data': responseData}
    json_responseBody = json.dumps(responseBody)
    print("Response body:\\n" + json_responseBody)
    headers = {
        'content-type' : '',
        'content-length' : str(len(json_responseBody))
    }
    try:
        response = http.request('PUT', responseUrl, headers=headers, body=json_responseBody)
        print("Status code:", response.status)
    except Exception as e:
        print("send(..) failed executing http.request(..):", e)
"""),
                                   handler="index.lambda_handler",
                                   runtime=Runtime.PYTHON_3_9,
                                   timeout=Duration.seconds(30),
                                   role=lambda_role
                                   )

        # Custom resource
        custom_resource = CustomResource(
            self, "LambdaTrigger",
            service_token=lambda_function.function_arn,
        )
        custom_resource.node.add_dependency(asg)

        # Dependencies
        lambda_role.node.add_dependency(asg)
        custom_resource.node.add_dependency(lambda_role)


        CfnOutput(self, 'OpensearchDashboardUrl',
                  description='Opensearch Dashboard URL',
                  value=Fn.join("", [
                      "https://",
                      custom_resource.get_att_string('PublicIpAddress'),
                      "/_dashboards"
                  ]))

        CfnOutput(self, 'OpensearchDomainEndpoint',
                  description='Opensearch Dashboard URL',
                  value=domain.get_att('DomainEndpoint').to_string()
                  )
        self.opensearch_domain_endpoint = domain.get_att('DomainEndpoint').to_string()

        CfnOutput(self, 'PipelineRoleArn',
                  description='Role ARN to use by the Opensearch Ingestion pipeline',
                  value=pipeline_role.role_arn
                  )
        self.pipeline_role_arn = pipeline_role.role_arn

        CfnOutput(self, 'OpensearchIndexes',
                  description='Indexes used in Opensearch to store logs and metrics',
                  value='spark-logs, spark-metrics'
                  )
