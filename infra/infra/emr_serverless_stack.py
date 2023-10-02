from os.path import dirname, join

import cdk_ecr_deployment as ecr_deploy
from aws_cdk import (
    Duration,
    Fn,
    RemovalPolicy,
    Stack,
    aws_iam as iam,
    aws_s3 as s3,
    aws_emrserverless as emr,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_events as events,
    aws_events_targets as targets, CfnOutput,
    aws_ecr_assets as ecr_assets,
    aws_ecr as ecr,
)
from aws_cdk.aws_ec2 import Vpc, SecurityGroup, Peer, Port, SubnetSelection, SubnetType
from constructs import Construct


class EmrServerlessStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Stack, needed to get region and account ID
        stack = Stack.of(self)

        # EMR serverless execution role
        emr_role = iam.Role(
            self, 'EmrRole',
            assumed_by=iam.ServicePrincipal('emr-serverless.amazonaws.com')
        )
        # Get the ingestion pipeline managed policy from context or parameter
        collector_policy_arn = self.node.try_get_context('CollectorPolicyArn')
        if collector_policy_arn is None:
            raise Exception("CollectorPolicyArn context parameter must be set")


        emr_role.add_managed_policy(iam.ManagedPolicy.from_managed_policy_arn(self, 'CollectorPolicy', collector_policy_arn))

        # Public bucket used for source data
        source_bucket = s3.Bucket.from_bucket_name(self, "SourceBucket", "blogpost-sparkoneks-us-east-1")
        source_bucket.grant_read(emr_role, "blog/BLOG_TPCDS-TEST-3T-partitioned*")

        # Artifact bucket used for Spark jar
        artifact_bucket = s3.Bucket.from_bucket_name(self, "ArtifactBucket", "aws-bigdata-blog")
        artifact_bucket.grant_read(emr_role, 'artifacts/oss-spark-benchmarking/spark-benchmark-assembly-3.3.0.jar')

        # Destination bucket for storing results data and logs
        destination_bucket = s3.Bucket(self, 'DestinationBucket', auto_delete_objects=True, removal_policy=RemovalPolicy.DESTROY)
        destination_bucket.grant_read_write(emr_role)

        emr_custom_repo_name = 'emr-6.9-observability'
        # Create the ECR repository (required to grant emr-serverless with resource based policy)
        emr_custom_repo = ecr.Repository(self, 'EmrEcr', repository_name=emr_custom_repo_name,
                                         removal_policy=RemovalPolicy.DESTROY,
                                         auto_delete_images=True
                                         )

        # EMR custom image with log4j2.properties file
        emr_custom_image = ecr_assets.DockerImageAsset(self, 'EmrCustomImage',
                                                       directory=join(dirname(dirname(__file__)), 'docker')
                                                       )
        emr_image_deployment = ecr_deploy.ECRDeployment(self, 'EmrCustomImageDeploy',
                                                      src=ecr_deploy.DockerImageName(emr_custom_image.image_uri),
                                                      dest=ecr_deploy.DockerImageName(f"{emr_custom_repo.repository_uri}:latest")
                                                      )

        # Get the VPC from parameter or create a new one
        vpc_id_param = scope.node.try_get_context("VpcID")
        if vpc_id_param is not None:

            vpc = Vpc.from_lookup(self, 'Vpc', vpc_id=vpc_id_param)

            sec_group = SecurityGroup(self, 'PipelineSecurityGroup', vpc=vpc, allow_all_outbound=True)

            # Get the Subnets from parameters or takes private ones from the Vpc with one per AZ.
            subnets_ids_param = scope.node.try_get_context("SubnetsIDs")
            if subnets_ids_param is None:
                subnets = SubnetSelection(
                    subnets=vpc.select_subnets(one_per_az=True, subnet_type=SubnetType.PRIVATE_WITH_EGRESS).subnets)
                subnets_ids = list(map(lambda subnet: subnet.subnet_id, subnets.subnets))
            else:
                subnets_ids = subnets_ids_param.split(',')

            # EMR serverless application
            emr_serverless = emr.CfnApplication(self, "EmrServerless",
                                                name="emr-serverless-demo",
                                                image_configuration=emr.CfnApplication.ImageConfigurationInputProperty(
                                                    image_uri=f"{stack.account}.dkr.ecr.{stack.region}.amazonaws.com/{emr_custom_repo_name}:latest"
                                                ),
                                                architecture='X86_64',
                                                auto_start_configuration=emr.CfnApplication.AutoStartConfigurationProperty(enabled=True),
                                                auto_stop_configuration=emr.CfnApplication.AutoStopConfigurationProperty(
                                                    enabled=True,
                                                    idle_timeout_minutes=1
                                                ),
                                                release_label="emr-6.9.0",
                                                type="Spark",
                                                network_configuration=emr.CfnApplication.NetworkConfigurationProperty(
                                                    security_group_ids=[sec_group.security_group_id],
                                                    subnet_ids=subnets_ids
                                                ),
                                                maximum_capacity=emr.CfnApplication.MaximumAllowedResourcesProperty(
                                                    cpu="2000vcpu",
                                                    memory="10000gb",
                                                    disk="32000gb"
                                                ))
        else:
            emr_serverless = emr.CfnApplication(self, "EmrServerless",
                                                name="emr-serverless-demo",
                                                image_configuration=emr.CfnApplication.ImageConfigurationInputProperty(
                                                    image_uri=f"{stack.account}.dkr.ecr.{stack.region}.amazonaws.com/{emr_custom_repo_name}:latest"
                                                ),
                                                architecture='X86_64',
                                                auto_start_configuration=emr.CfnApplication.AutoStartConfigurationProperty(enabled=True),
                                                auto_stop_configuration=emr.CfnApplication.AutoStopConfigurationProperty(
                                                    enabled=True,
                                                    idle_timeout_minutes=1
                                                ),
                                                release_label="emr-6.9.0",
                                                type="Spark",
                                                maximum_capacity=emr.CfnApplication.MaximumAllowedResourcesProperty(
                                                    cpu="2000vcpu",
                                                    memory="10000gb",
                                                    disk="32000gb"
                                                ))

        emr_serverless.node.add_dependency(emr_image_deployment)

        # Get the OSIS pipeline from CDK parameters or context
        metrics_ingestion_url = self.node.try_get_context('MetricsPipelineUrl')

        # StepFunctions task to trigger the EMR serverless application with entrypoint and dependencies archive
        # Removed the jar file deployed on S3 because it's already in the docker image
        # --conf spark.jars=s3://{jar_file.deployed_bucket.bucket_name}/{Fn.select(0,jar_file.object_keys)}
        emr_start_job_task = tasks.CallAwsService(self, 'EmrStartJobTask',
                                                  service='emrserverless',
                                                  action='startJobRun',
                                                  # Needs to be enforced https://github.com/aws/aws-cdk/issues/23824
                                                  iam_action='emr-serverless:StartJobRun',
                                                  iam_resources=[emr_serverless.attr_arn],
                                                  parameters={
                                                      "Name": sfn.JsonPath.format('tpcds-{}', sfn.JsonPath.uuid()),
                                                      "ApplicationId": emr_serverless.attr_application_id,
                                                      "ClientToken": sfn.JsonPath.uuid(),
                                                      "ConfigurationOverrides": {
                                                          "MonitoringConfiguration": {
                                                              "S3MonitoringConfiguration": {
                                                                  "LogUri": destination_bucket.s3_url_for_object("logs/")
                                                              }
                                                          }
                                                      },
                                                      "ExecutionRoleArn": emr_role.role_arn,
                                                      "ExecutionTimeoutMinutes": 120,
                                                      "JobDriver": {
                                                          "SparkSubmit": {
                                                              "EntryPoint": "s3://aws-bigdata-blog/artifacts/oss-spark-benchmarking/spark-benchmark-assembly-3.3.0.jar",
                                                              "EntryPointArguments": ["s3://blogpost-sparkoneks-us-east-1/blog/BLOG_TPCDS-TEST-3T-partitioned", f"s3://{destination_bucket.bucket_name}/EMRSERVERLESS_TPCDS-TEST-3T-RESULT","/opt/tpcds-kit/tools","parquet","3000","1","false","q1-v2.4,q10-v2.4,q11-v2.4,q12-v2.4,q13-v2.4,q14a-v2.4,q14b-v2.4,q15-v2.4,q16-v2.4,q17-v2.4,q18-v2.4,q19-v2.4,q2-v2.4,q20-v2.4,q21-v2.4,q22-v2.4,q23a-v2.4,q23b-v2.4,q24a-v2.4,q24b-v2.4,q25-v2.4,q26-v2.4,q27-v2.4,q28-v2.4,q29-v2.4,q3-v2.4,q30-v2.4,q31-v2.4,q32-v2.4,q33-v2.4,q34-v2.4,q35-v2.4,q36-v2.4,q37-v2.4,q38-v2.4,q39a-v2.4,q39b-v2.4,q4-v2.4,q40-v2.4,q41-v2.4,q42-v2.4,q43-v2.4,q44-v2.4,q45-v2.4,q46-v2.4,q47-v2.4,q48-v2.4,q49-v2.4,q5-v2.4,q50-v2.4,q51-v2.4,q52-v2.4,q53-v2.4,q54-v2.4,q55-v2.4,q56-v2.4,q57-v2.4,q58-v2.4,q59-v2.4,q6-v2.4,q60-v2.4,q61-v2.4,q62-v2.4,q63-v2.4,q64-v2.4,q65-v2.4,q66-v2.4,q67-v2.4,q68-v2.4,q69-v2.4,q7-v2.4,q70-v2.4,q71-v2.4,q72-v2.4,q73-v2.4,q74-v2.4,q75-v2.4,q76-v2.4,q77-v2.4,q78-v2.4,q79-v2.4,q8-v2.4,q80-v2.4,q81-v2.4,q82-v2.4,q83-v2.4,q84-v2.4,q85-v2.4,q86-v2.4,q87-v2.4,q88-v2.4,q89-v2.4,q9-v2.4,q90-v2.4,q91-v2.4,q92-v2.4,q93-v2.4,q94-v2.4,q95-v2.4,q96-v2.4,q97-v2.4,q98-v2.4,q99-v2.4,ss_max-v2.4","true"],
                                                              "SparkSubmitParameters": f"--conf spark.driver.extraJavaOptions=-Dlog4j2.contextSelector=org.apache.logging.log4j.core.async.AsyncLoggerContextSelector --conf spark.executor.extraJavaOptions=-Dlog4j2.contextSelector=org.apache.logging.log4j.core.async.AsyncLoggerContextSelector --conf spark.extraListeners=com.amazonaws.sparkobservability.CustomMetricsListener --conf spark.metrics.region={stack.region} --conf spark.metrics.endpoint={metrics_ingestion_url} --conf spark.metrics.batchSize=400 --conf spark.metrics.timeThreshold=60 --conf spark.dynamicAllocation.initialExecutors=20 --class com.amazonaws.eks.tpcds.BenchmarkSQL"
                                                          },
                                                      }
                                                  },
                                                  result_selector={
                                                      "JobRunId.$": "$.JobRunId"
                                                  }
                                                  )
        # TODO wait for job completion and test result
        wait = sfn.Wait(self, 'WaitForEmrJobCompletion',
                        time=sfn.WaitTime.duration(Duration.seconds(30))
                        )

        emr_job_status_task = tasks.CallAwsService(self, 'EmrJobStatusTask',
                                                   service='emrserverless',
                                                   action='getJobRun',
                                                   # Needs to be enforced https://github.com/aws/aws-cdk/issues/23824
                                                   iam_action='emr-serverless:GetJobRun',
                                                   iam_resources=[Fn.join("", [emr_serverless.attr_arn, "/jobruns/*"])],
                                                   parameters={
                                                       "ApplicationId": emr_serverless.attr_application_id,
                                                       "JobRunId": sfn.JsonPath.string_at("$.JobRunId"),
                                                   },
                                                   result_selector={
                                                       "State.$": "$.JobRun.State",
                                                       "StateDetails.$": "$.JobRun.StateDetails"
                                                   },
                                                   result_path="$.JobRunState"
                                                   )

        job_failed = sfn.Fail(self, 'JobFailed',
                              cause="EMR Job Failed",
                              error=sfn.JsonPath.string_at("$.JobRunState.StateDetails"),
                              )

        job_succeeded = sfn.Succeed(self, 'JobSucceeded')

        emr_pipeline_chain = emr_start_job_task.next(wait).next(emr_job_status_task).next(sfn.Choice(self, 'JobSucceededOrFailed')
                                                                                          .when(sfn.Condition.string_equals("$.JobRunState.State", "SUCCESS"), job_succeeded)
                                                                                          .when(sfn.Condition.string_equals("$.JobRunState.State", "FAILED"), job_failed)
                                                                                          .when(sfn.Condition.string_equals("$.JobRunState.State", "CANCELLED"), job_failed)
                                                                                          .otherwise(wait)
                                                                                          )

        # StepFunctions state machine
        emr_pipeline = sfn.StateMachine(self, "EmrPipeline",
                                        definition=emr_pipeline_chain,
                                        )
        # Grant the Step Functions role to pull image for EMR Serverless custom image
        emr_custom_repo.grant_pull(emr_pipeline.role)
        emr_custom_repo.add_to_resource_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:BatchGetImage",
                    "ecr:DescribeImages",
                    "ecr:GetDownloadUrlForLayer"
                ],
                principals=[
                    iam.ServicePrincipal('emr-serverless.amazonaws.com')
                ]
            )
        )

        # Grant the StepFunctions role to assume the EMR serverless role
        emr_role.grant_pass_role(emr_pipeline)

        emr_pipeline_trigger = events.Rule(self, "EmrPipelineTrigger",
                                           schedule=events.Schedule.rate(Duration.minutes(1440)),
                                           targets=[targets.SfnStateMachine(emr_pipeline)]
                                           )

        # Outputs used by the CDK Pipeline stack to trigger the job
        CfnOutput(self, 'EmrServerlessAppId', value=emr_serverless.attr_application_id)
        CfnOutput(self, 'EmrServerlessRole', value=emr_role.role_arn)
        CfnOutput(self, 'DestinationBukcet', value=destination_bucket.bucket_name)