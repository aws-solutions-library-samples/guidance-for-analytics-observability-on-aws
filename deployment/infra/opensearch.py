# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0



from aws_cdk import (
    Stack, CfnTag, )
from aws_cdk.aws_iam import ManagedPolicy, PolicyStatement, ServicePrincipal, \
    Role, IRole
from aws_cdk.aws_opensearchservice import CfnDomain
from constructs import Construct


from infra.cluster_sizing import ClusterConfig
from infra.opensearch_prereq import OpensearchPreReq


class Opensearch(Construct):
    
    @property
    def domain(self):
        return self.__domain
    
    @property
    def pipeline_role(self):
        return self.__pipeline_role

    def __init__(self,
                 scope: Construct, 
                 id: str,
                 prereq: OpensearchPreReq,
                 admin_role: IRole,
                 cluster_sizing: ClusterConfig,
                 **kwargs):
        super().__init__(scope, id, **kwargs)

        # Stack, needed to get region and account ID
        stack = Stack.of(self)

        self.__domain = CfnDomain(self, "SparkObservabilityDomain",
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
                                   master_user_arn=admin_role.role_arn,
                               )
                           ),
                           cluster_config=cluster_sizing.cluster_config,
                           domain_endpoint_options=CfnDomain.DomainEndpointOptionsProperty(
                               custom_endpoint_enabled=False,
                               enforce_https=True,
                               tls_security_policy="Policy-Min-TLS-1-2-2019-07"
                           ),
                           domain_name=prereq.domain_name,
                           ebs_options=cluster_sizing.ebs_config,
                           encryption_at_rest_options=CfnDomain.EncryptionAtRestOptionsProperty(
                               enabled=True,
                               kms_key_id=prereq.domain_key.key_id
                           ),
                           engine_version="OpenSearch_2.7",
                           node_to_node_encryption_options=CfnDomain.NodeToNodeEncryptionOptionsProperty(
                               enabled=True
                           ),
                           vpc_options=CfnDomain.VPCOptionsProperty(
                               subnet_ids=list(map(lambda subnet: subnet.subnet_id, prereq.domain_subnets.subnets)),
                               security_group_ids=[prereq.domain_security_group.security_group_id]
                           ),
                           log_publishing_options={
                                'SEARCH_SLOW_LOGS': CfnDomain.LogPublishingOptionProperty(
                                    cloud_watch_logs_log_group_arn= prereq.domain_log_group.log_group_arn,
                                    enabled= True,
                                ),
                                'INDEX_SLOW_LOGS': CfnDomain.LogPublishingOptionProperty(
                                    cloud_watch_logs_log_group_arn= prereq.domain_log_group.log_group_arn,
                                    enabled= True,
                                )
                           },
                           tags=[CfnTag(
                               key="spark-observability",
                               value="true"
                           )],
                           )
        
        # The role used by the Opensearch Ingestion pipeline
        self.__pipeline_role = Role(self, 'PipelineRole',
                             assumed_by=ServicePrincipal('osis-pipelines.amazonaws.com'))

        # the policy attached to the OS ingestion pipeline
        ManagedPolicy(self, 'PipelinePolicy',
                      statements=[
                          PolicyStatement(
                              resources=[f"arn:aws:es:{stack.region}:{stack.account}:domain/{prereq.domain_name}"],
                              actions=["es:DescribeDomain"],
                          ),
                          PolicyStatement(
                              resources=[self.__domain.get_att('Arn').to_string() + '/*'],
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
                      roles=[self.__pipeline_role]
                      )