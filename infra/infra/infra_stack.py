import subprocess
import json

from aws_cdk import (
    Stack, RemovalPolicy, CfnOutput, CfnTag, Fn, Duration, CustomResource, Aws,
)
from aws_cdk.aws_ec2 import Vpc
from aws_cdk.aws_secretsmanager import Secret, SecretStringGenerator
from aws_cdk.aws_iam import CfnServiceLinkedRole, AnyPrincipal, ManagedPolicy, PolicyStatement, ServicePrincipal, Role, \
    Effect
from aws_cdk.aws_osis import CfnPipeline
from aws_cdk.aws_kms import Key
from aws_cdk.aws_lambda import LayerVersion, Code, Runtime, Function
from aws_cdk.aws_logs import LogGroup, RetentionDays
from aws_cdk.aws_opensearchservice import CfnDomain
from aws_cdk.custom_resources import Provider
from constructs import Construct

from infra.cluster_sizing import ClusterConfig
from pathlib import Path


class InfraStack(Stack):

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
                                   'service-role/AWSLambdaBasicExecutionRole')
                           ])

        # add permission to update the cluster after creation. required to enable FGAC with internal database users
        master_role.add_to_policy(
            PolicyStatement(
                actions=['es:UpdateElasticsearchDomainConfig'],
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

        # Create a default VPC with 3 AZs
        # You need to set the env variables in the app.py to get effectively 3 AZs, otherwise you only get 2
        # TODO: CfnOutput + export value for VPC connectivity
        vpc = Vpc(self, 'Vpc', max_azs=3)

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
                           engine_version="OpenSearch_2.3",
                           log_publishing_options={
                               "INDEX_SLOW_LOGS": CfnDomain.LogPublishingOptionProperty(
                                   cloud_watch_logs_log_group_arn=log_group.log_group_arn,
                                   enabled=True
                               ),
                               "SEARCH_SLOW_LOGS": CfnDomain.LogPublishingOptionProperty(
                                   cloud_watch_logs_log_group_arn=log_group.log_group_arn,
                                   enabled=True
                               ),
                               "AUDIT_LOGS": CfnDomain.LogPublishingOptionProperty(
                                   cloud_watch_logs_log_group_arn=log_group.log_group_arn,
                                   enabled=True
                               ),
                               "ES_APPLICATION_LOGS": CfnDomain.LogPublishingOptionProperty(
                                   cloud_watch_logs_log_group_arn=log_group.log_group_arn,
                                   enabled=True
                               ),
                               "TASK_DETAILS_LOGS": CfnDomain.LogPublishingOptionProperty(
                                   cloud_watch_logs_log_group_arn=log_group.log_group_arn,
                                   enabled=True
                               )
                           },
                           node_to_node_encryption_options=CfnDomain.NodeToNodeEncryptionOptionsProperty(
                               enabled=True
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
                                                # conditions={
                                                #     "StringEquals": {
                                                #         "aws:SourceAccount": stack.account
                                                #     },
                                                #     "ArnLike": {
                                                #         "aws:SourceArn": f"arn:aws:osis:{stack.region}:{stack.account}:pipeline/*"
                                                #     }
                                                # }
                                            ),
                                            PolicyStatement(
                                                resources=[domain.get_att('Arn').to_string() + '/*'],
                                                actions=["es:ESHttp*"],
                                                # conditions={
                                                #     "StringEquals": {
                                                #         "aws:SourceAccount": stack.account
                                                #     },
                                                #     "ArnLike": {
                                                #         "aws:SourceArn": f"arn:aws:osis:{stack.region}:{stack.account}:pipeline/*"
                                                #     }
                                                # }
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
                                    role=master_role
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

        # Policy for the ingestor component
        collector_policy = ManagedPolicy(self, 'CollectorPolicy',
                                         statements=[
                                             PolicyStatement(
                                                 actions=['osis:Ingest'],
                                                 resources=[
                                                     f'arn:aws:osis:{stack.region}:{stack.account}:pipeline/spark-obs-logs',
                                                     f'arn:aws:osis:{stack.region}:{stack.account}:pipeline/spark-obs-metrics'
                                                 ]
                                             ),
                                         ])

        # OSI pipeline for logs
        logs_pipeline = CfnPipeline(self, 'LogsPipeline',
                                   max_units=10,
                                   min_units=1,
                                   pipeline_configuration_body='''
                                      version: "2"
                                      pipeline:
                                          source:
                                            http:
                                              path: "/ingest"
                                          processor:
                                            - date:
                                                from_time_received: true
                                                destination: "@timestamp"
                                          sink:
                                            - opensearch:
                                                hosts: [ "https://{domain_url}" ]
                                                index: "spark-logs"
                                                aws_sts_role_arn: "{role_arn}"
                                                aws_region: "{region}"
                                                aws_sigv4: true
                                   '''.format(
                                       domain_url=domain.get_att('DomainEndpoint').to_string(),
                                       role_arn=pipeline_role.role_arn,
                                       region=stack.region
                                   ),
                                   pipeline_name="spark-obs-logs",
                                   )

        # OSI pipeline for metrics
        metrics_pipeline = CfnPipeline(self, 'MetricsPipeline',
                                       max_units=4,
                                       min_units=1,
                                       pipeline_configuration_body='''
                                            version: "2"
                                            pipeline:
                                              source:
                                                http:
                                                  path: "/ingest"
                                              processor:
                                                - date:
                                                    from_time_received: true
                                                    destination: "@timestamp"
                                              sink:
                                                - opensearch:
                                                    hosts: [ "https://{domain_url}" ]
                                                    index: "spark-metrics"
                                                    aws_sts_role_arn: "{role_arn}"
                                                    aws_region: "{region}"
                                                    aws_sigv4: true
                                           '''.format(
                                           domain_url=domain.get_att('DomainEndpoint').to_string(),
                                           role_arn=pipeline_role.role_arn,
                                           region=stack.region
                                       ),
                                       pipeline_name="spark-obs-metrics",
                                       )

        CfnOutput(self, 'OpensearchDashboardUrl',
                  description='Opensearch Dashboard URL',
                  value=Fn.join('', ['https://', domain.get_att('DomainEndpoint').to_string(), '/_dashboards'])
                  )

        CfnOutput(self, 'CollectorPolicyArn',
                  description='Collector managed policy ARN to attach to the role used by the Spark job',
                  value=collector_policy.managed_policy_arn,
                  )

        CfnOutput(self, 'OsisRole',
                  description='Role to use by the Osis pipeline',
                  value=pipeline_role.role_arn
                  )

        CfnOutput(self, 'OsisPipelineIndex',
                  description='Indexes used in Opensearch',
                  value='spark-logs, spark-metrics'
                  )

        # TODO replace ARn with endpoint URL when bug corrected
        CfnOutput(self, 'MetricsPipelineUrl',
                  description='Pipeline endpoint for metrics',
                  # value=Fn.join('', ['https://', metrics_pipeline.get_att('IngestionUrls').to_string(), '/ingest']),
                  value=metrics_pipeline.get_att('PipelineArn').to_string(),
                  export_name='metrics-endpoint'
                  )

        CfnOutput(self, 'LogsPipelineUrl',
                  description='Pipeline endpoint for logs',
                  # value=Fn.join('', ['https://', logs_pipeline.get_att('IngestionUrls').to_string(), '/ingest']),
                  value=logs_pipeline.get_att('PipelineArn').to_string(),
                  export_name='logs-endpoint'
                  )
