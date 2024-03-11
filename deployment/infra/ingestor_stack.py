# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    Aspects, Stack, CfnOutput, Fn, RemovalPolicy, Names, UniqueResourceNameOptions,
)
from aws_cdk.aws_ec2 import Vpc, SubnetSelection, SubnetType, SecurityGroup, Peer, Port, SubnetFilter
from aws_cdk.aws_iam import ManagedPolicy, PolicyStatement, ServicePrincipal
from aws_cdk.aws_logs import LogGroup, RetentionDays
from aws_cdk.aws_osis import CfnPipeline
from constructs import Construct
from cdk_nag import AwsSolutionsChecks, NagSuppressions


class IngestorStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Stack, needed to get region and account ID
        stack = Stack.of(self)

        pipeline_role_arn = self.node.try_get_context('PipelineRoleArn')
        if pipeline_role_arn is None:
            raise Exception("PipelineRoleArn context parameter must be set")

        opensearch_domain_endpoint = self.node.try_get_context('OpensearchDomainEndpoint')
        if opensearch_domain_endpoint is None:
            raise Exception("OpensearchDomainEndpoint context parameter must be set")

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

        logs_log_group = LogGroup(self, 'LogsIngestionLogGroup',
                                  removal_policy=RemovalPolicy.DESTROY,
                                  retention=RetentionDays.ONE_WEEK,
                                  log_group_name="/aws/vendedlogs/osis-logs-" + Names.unique_resource_name(self).lower()
                                  )
        logs_log_group.grant_write(ServicePrincipal("es.amazonaws.com"))

        metrics_log_group = LogGroup(self, 'MetricsIngestionLogGroup',
                                     removal_policy=RemovalPolicy.DESTROY,
                                     retention=RetentionDays.ONE_WEEK,
                                     log_group_name="/aws/vendedlogs/osis-metrics-" + Names.unique_resource_name(self).lower()
                                     )
        metrics_log_group.grant_write(ServicePrincipal("es.amazonaws.com"))

        # Get the VPC from parameter or create a new one
        vpc_id_param = scope.node.try_get_context("VpcID")
        if vpc_id_param is not None:

            vpc = Vpc.from_lookup(self, 'IngestionVpc', vpc_id=vpc_id_param)

            # Get the Subnets from parameters or takes private ones from the Vpc with one per AZ.
            subnets_ids_param = scope.node.try_get_context("SubnetsIDs")
            if subnets_ids_param is None:
                subnets = SubnetSelection(
                    subnets=vpc.select_subnets(one_per_az=True, subnet_type=SubnetType.PRIVATE_WITH_EGRESS).subnets)
                subnets_ids = list(map(lambda subnet: subnet.subnet_id, subnets.subnets))
            else:
                subnets_ids = subnets_ids_param.split(',')

            sec_group = SecurityGroup(self, 'PipelineSecurityGroup', vpc=vpc)

            sec_group.add_ingress_rule(
                peer=Peer.ipv4('0.0.0.0/0'),
                connection=Port.tcp(443)
            )

            # OSI pipeline for logs
            logs_pipeline = CfnPipeline(self, 'LogsPipeline',
                                        max_units=10,
                                        min_units=1,
                                        pipeline_configuration_body=open(
                                            './infra/resources/pipelines/logs-pipeline.yaml')
                                        .read()
                                        .format(
                                            domain_url=opensearch_domain_endpoint,
                                            role_arn=pipeline_role_arn,
                                            region=stack.region
                                        ),
                                        pipeline_name="spark-obs-logs",
                                        log_publishing_options=CfnPipeline.LogPublishingOptionsProperty(
                                            cloud_watch_log_destination=CfnPipeline.CloudWatchLogDestinationProperty(
                                                log_group=logs_log_group.log_group_name
                                            ),
                                            is_logging_enabled=True
                                        ),
                                        vpc_options=CfnPipeline.VpcOptionsProperty(
                                            security_group_ids=[sec_group.security_group_id],
                                            subnet_ids=subnets_ids,
                                        ))

            # OSI pipeline for metrics
            metrics_pipeline = CfnPipeline(self, 'MetricsPipeline',
                                           max_units=4,
                                           min_units=1,
                                           pipeline_configuration_body=open(
                                               './infra/resources/pipelines/metrics-pipeline.yaml')
                                           .read()
                                           .format(
                                               domain_url=opensearch_domain_endpoint,
                                               role_arn=pipeline_role_arn,
                                               region=stack.region
                                           ),
                                           pipeline_name="spark-obs-metrics",
                                           log_publishing_options=CfnPipeline.LogPublishingOptionsProperty(
                                               cloud_watch_log_destination=CfnPipeline.CloudWatchLogDestinationProperty(
                                                   log_group=metrics_log_group.log_group_name
                                               ),
                                               is_logging_enabled=True
                                           ),
                                           vpc_options=CfnPipeline.VpcOptionsProperty(
                                               security_group_ids=[sec_group.security_group_id],
                                               subnet_ids=subnets_ids,
                                           ))
        else:
            # OSI pipelines are public
            logs_pipeline = CfnPipeline(self, 'LogsPipeline',
                                        max_units=10,
                                        min_units=1,
                                        pipeline_configuration_body=open(
                                            './infra/resources/pipelines/logs-pipeline.yaml')
                                        .read()
                                        .format(
                                            domain_url=opensearch_domain_endpoint,
                                            role_arn=pipeline_role_arn,
                                            region=stack.region
                                        ),
                                        pipeline_name="spark-obs-logs",
                                        log_publishing_options=CfnPipeline.LogPublishingOptionsProperty(
                                            cloud_watch_log_destination=CfnPipeline.CloudWatchLogDestinationProperty(
                                                log_group=logs_log_group.log_group_name
                                            ),
                                            is_logging_enabled=True
                                        ),
                                        )

            # OSI pipeline for metrics
            metrics_pipeline = CfnPipeline(self, 'MetricsPipeline',
                                           max_units=4,
                                           min_units=1,
                                           pipeline_configuration_body=open(
                                               './infra/resources/pipelines/metrics-pipeline.yaml')
                                           .read()
                                           .format(
                                               domain_url=opensearch_domain_endpoint,
                                               role_arn=pipeline_role_arn,
                                               region=stack.region
                                           ),
                                           pipeline_name="spark-obs-metrics",
                                           log_publishing_options=CfnPipeline.LogPublishingOptionsProperty(
                                               cloud_watch_log_destination=CfnPipeline.CloudWatchLogDestinationProperty(
                                                   log_group=metrics_log_group.log_group_name
                                               ),
                                               is_logging_enabled=True
                                           ),
                                           )

        CfnOutput(self, 'MetricsPipelineUrl',
                  description='Pipeline endpoint for metrics',
                  value=Fn.join('', ['https://', Fn.select(0, metrics_pipeline.attr_ingest_endpoint_urls), '/ingest']),
                  )

        CfnOutput(self, 'LogsPipelineUrl',
                  description='Pipeline endpoint for logs',
                  value=Fn.join('', ['https://', Fn.select(0, logs_pipeline.attr_ingest_endpoint_urls), '/ingest']),
                  )

        CfnOutput(self, 'CollectorPolicyArn',
                  description='Collector managed policy ARN to attach to the role used by the Spark job',
                  value=collector_policy.managed_policy_arn,
                  )

        Aspects.of(self).add(AwsSolutionsChecks())

        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/IngestorStack/PipelineSecurityGroup/Resource', suppressions=[
            {"id": "AwsSolutions-EC23", "reason": "The ingestor source is not predictable when deploying the ingestor stack."},
        ])