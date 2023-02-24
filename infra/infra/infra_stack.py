from aws_cdk import (
    Stack, RemovalPolicy, CfnOutput, CfnTag, Fn,
)
from aws_cdk.aws_ec2 import Vpc
from aws_cdk.aws_iam import CfnServiceLinkedRole, AnyPrincipal, ManagedPolicy, PolicyStatement
from aws_cdk.aws_kms import Key
from aws_cdk.aws_logs import LogGroup, RetentionDays
from aws_cdk.aws_opensearchservice import CfnDomain
from constructs import Construct

from infra.cluster_sizing import ClusterConfig
from infra.security_options import SecurityOptions


class InfraStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Parameter for the Opensearch Dashboard authentication
        self.__auth_mode = SecurityOptions.load_auth_mode(self.node.try_get_context("AuthMode"))

        # Opensearch domain security config and additional resources if required (secret)
        security_config = SecurityOptions(self, 'DomainSecurityOptions', self.__auth_mode)

        # Parameter for T-shirt sizing the Opensearch domain
        self.__tshirt_size = ClusterConfig.load_tshirt_size(self.node.try_get_context("TshirtSize"))
        cluster_sizing = ClusterConfig(self.__tshirt_size)

        # Service Linked role for Amazon Opensearch
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

        # Log group for the Opensearch domain
        log_group = LogGroup(self, 'OpensearchLogGroup',
                             removal_policy=RemovalPolicy.DESTROY,
                             retention=RetentionDays.ONE_WEEK,
                             log_group_name='spark-observability-logs',
                             )

        domain = CfnDomain(self, "MyCfnDomain",
                           # access_policies=access_policies,
                           advanced_options={
                               "rest.action.multi.allow_explicit_index": "false"
                           },
                           advanced_security_options=security_config.config,
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

        # Policy for the spark job to ingest data
        collector_policy = ManagedPolicy(self,'CollectorPolicy',
                                         statements=[
                                             PolicyStatement(
                                                 actions=['es:DescribeDomain'],
                                                 resources=[domain.get_att('Arn').to_string()]
                                             ),
                                             PolicyStatement(
                                                 actions=['es:ESHttp*'],
                                                 resources=[
                                                     domain.get_att('Arn').to_string()+'/index*',
                                                     domain.get_att('Arn').to_string()+'/_template/index*',
                                                     domain.get_att('Arn').to_string()+'/_plugins/_ism/policies/*'
                                                 ]
                                             ),
                                             PolicyStatement(
                                                 actions=['es:ESHttpGet'],
                                                 resources=[
                                                     domain.get_att('Arn').to_string()+'/_cluster/settings',
                                                 ]
                                             ),
                                         ]
                                         )

        CfnOutput(self, 'OpensearchDashboardUrl',
                  description='Opensearch Dashboard URL',
                  value=Fn.join('', ['https://', domain.get_att('DomainEndpoint').to_string(), '/_dashboards'])
                  )

        CfnOutput(self, 'OpensearchAdminPasswordSecretArn',
                  description='Opensearch admin password secret ARN',
                  value=security_config.secret.secret_arn
                  )

        CfnOutput(self, 'CollectorPolicyArn',
                  description='Collector managed policy ARN',
                  value=collector_policy.managed_policy_arn
                  )
