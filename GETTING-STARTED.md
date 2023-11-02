# Getting started

![AWS Spark Observability architecture](./static/spark-observability.png)

The recommended order of deployment is:
2. Deploy the CDK stacks that fits your need:
   1. The backend (OPTIONAL). Alternatively you can provide your own Amazon Opensearch Domain.
   2. A generic VPC (OPTIONAL). Alternatively you can provide your own VPC. This is where deploy your Spark application.
   3. The ingestor (REQUIRED). It should be deployed in the same VPC and subnets as your Spark application.
   4. Deploy the EMR Serverless example (OPTIONAL). Alternatively configure your Spark application with the collector that you built and run it.
3. Analyze data in Opensearch Dashboards


## Pre-requisite

 * SBT. If you don't have SBT, install from [here](https://www.scala-sbt.org/download.html)
 * AWS CDK. If you don't CDK, follow [these instructions](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html#getting_started_install)

## Deploy the backend components

Go into the `infra` folder.

The `cdk.json` file tells the CDK Toolkit how to execute your app.

This project is set up like a standard Python project.  The initialization
process also creates a virtualenv within this project, stored under the `.venv`
directory.  To create the virtualenv it assumes that there is a `python3`
(or `python` for Windows) executable in your path with access to the `venv`
package.

To manually create a virtualenv on MacOS and Linux:

```
python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```

Once the virtualenv is activated, you can install the required dependencies.

```
pip install -r requirements.txt
```

At this point you can now deploy stacks.

You select the stack to deploy using the `Stack` context parameter of CDK with the values `backend`, `vpc`, `ingestor` or `example`:
```bash
cdk deploy -c Stack=backend ...
cdk deploy -c Stack=vpc ...
cdk deploy -c Stack=ingestor ...
cdk deploy -c Stack=example ...
```

### Backend stack

The backend stack provides the following components:
 * A private Amazon Opensearch domain with Fine Grained Access Control enabled and internal database users
 * A Amazon VPC with 3 public and 3 private subnets, one per AZ, if no VPC is provided
 * An Amazon IAM Role with administrator privileges on the domain
 * An ingestion role with write permissions on logs and metrics indices in the Opensearch domain and used by the pipelines
 * User/password secrets in AWS Secret Manager for Opensearch Dashboards user and administrator
 * An Amazon KMS Key to encrypt the data in the Opensearch domain
 * An Amazon Cloudwatch Log Group to store logs from the Opensearch domain
 * A custom resource based on AWS Lambda to configure the Opensearch domain:
    * Configure the user and roles
    * Create the index mappings
    * Create the index templates  
    * Load the pre-defined dashboards

#### CDK context Parameters
 * `TshirtSize`: [REQUIRED] define the size of the Opensearch domain to deploy. Possible options are XS, S, M, L, XL.
 * `VpcID`: [OPTIONAL] the VPC ID where you want to deploy the backend infrastructure. 
   If not provided, the stack will create a VPC in 3 AZs with one public and one private subnet per AZ.
 * `OpensearchSubnetsIDs`: [OPTIONAL] the comma separated list of subnet IDs to use for deploying the backend infrastructure. 
   We recommend to use private subnets. If not provided, the stack will use one private subnet per AZ (up to 3 maximum AZs). 
 * `ReverseProxySubnetID`: [OPTIONAL] the public subnet ID to deploy the reverse proxy for accessing the Opensearch domain in the private subnet. 
   If not provided, the stack will use one public subnet. 
   
```bash
cdk deploy -c Stack=backend -c TshirtSize=XS -c VpcID=<MY_VPC_ID> -c OpensearchSubnetsIDs=<SUBNET_ID1>,<SUBNET_ID2> -c ReverseProxySubnetID=<SUBNET_ID3>
```

The CDK application outputs all the required information to use the backend:
 * The Opensearch Dashboard URL
 * The Opensearch domain endpoint (to be used in the ingestor stack)
 * The Opensearch indices used for logs and metrics
 * The ingestion IAM role ARN (to be used in the ingestor stack)

#### Opensearch domain TshirtSize

Here is the different configurations of the Opensearch domain based on the selected TshirtSize:
 * XS
   * No dedicated master
   * Single-AZ
   * 3x t3.small.search
   * 10GB of EBS GP3 disk per node
   
 * S
   * No dedicated masters
   * Multi-AZ
   * 3x m6g.large.search
   * 80GB of EBS GP3 disk per node
   
 * M
   * Dedicated masters
   * Multi-AZ
   * 3x c6g.large.search for master nodes
   * 3x r6g.xlarge.search for data nodes
   * 1x ultrawarm1.medium.search
   * 600GB of EBS GP3 disk per node

* L
   * Dedicated masters
   * Multi-AZ
   * 3x c6g.xlarge.search for master nodes
   * 3x r6g.4xlarge.search for data nodes
   * 1x ultrawarm1.large.search
   * 4TB of EBS GP3 disk per node

* XL
   * Dedicated masters
   * Multi-AZ
   * 5x c6g.2xlarge.search for master nodes
   * 12x r6g.4xlarge.search for data nodes
   * 4x ultrawarm1.large.search
   * 4TB of EBS GP3 disk per node

### VPC stack (optional)

This stack is only helpful when deploying the example. It provides a VPC that can be used to deploy the `ingestor` stack and the `example` stack.

The VPC stack provides the following components:
 * A VPC deployed within 1 availability zone
 * 1 public and 1 private subnet
 * 1 NAT gateway

### Ingestor stack

The ingestor stack provides the following components:
 * Two Opensearch Ingestion pipelines for ingesting logs and metrics respectively into an Opensearch domain
 * Two CloudWatch LogGroups for storing pipelines logs
 * An IAM policy to attach to the Spark job execution role with permissions to send logs and metrics to the Opensearch Ingestion pipelines

#### CDK context Parameters
 * `PipelineRoleArn`: [REQUIRED] the IAM role ARN with permissions to create Opensearch indices in a domain and write to them.  
 * `OpensearchDomainEndpoint`: [REQUIRED] the endpoint of the Opensearch domain that will store the indices
 * `VpcID`: [OPTIONAL] the VPC ID where to deploy the Opensearch ingestion pipeline. 
    If no VPC ID is provided, the ingestion pipeline is public.
 * `SubnetsIDs`: [OPTIONAL] the comma separated list of subnets IDs to deploy the Opensearch ingestion pipeline.
   If no subnets IDs are provided, it will use one private subnet per AZ from the provided VPC.


#### Provide your own Opensearch domain

If you provide your own Opensearch domain, you must ensure the pipeline role has the following trust relationship:

```
{
   "Effect": "Allow",
   "Principal": {
      "Service": "osis-pipelines.amazonaws.com"
   },
   "Action": "sts:AssumeRole"
}
```

And the following permissions:

```
{
    "Action": "es:DescribeDomain",
    "Resource": "arn:aws:es:*:<ACCOUNT_ID>:domain/*",
    "Effect": "Allow"
},
{
    "Condition": {
        "StringEquals": {
            "aws:SourceAccount": "<ACCOUNT_ID>"
        },
        "ArnLike": {
            "aws:SourceArn": "arn:aws:osis:<REGION>:<ACCOUNT_ID>:pipeline/*"
        }
    },
    "Action": "es:ESHttp*",
    "Resource": "arn:aws:es:<REGION>:<ACCOUNT_ID>:domain/spark-observability/*",
    "Effect": "Allow"
}
```

The CDK application outputs all the required information to configure your Spark applications:
 * The Opensearch Ingestion pipelines endpoints (one for logs and one for metrics)
 * The Policy ARN to attach to the Spark execution role


### EMR Serverless example stack (optional)

The EMR Serverless example is a stack demonstrating how to use the Spark Observability solution in EMR Serverless.
It's running a TPCDS benchmark that is configured to send logs and metrics to the `backend` stack via the `ingestor` stack.
The [Spark Observability collector](../../collector) is loaded when the Spark application starts.

The CDK application provisions the following components:
* An Amazon IAM Role used as the EMR Serverless execution role
* An IAM Policy imported from the collector policy ARN and attached to the EMR Serverless execution role
* Amazon S3 buckets for source (imported from public bucket) and destination (created)
* A custom docker image for EMR Serverless containing the collector JAR and the log4j2 configuration
* An Amazon ECR repository for storing the docker image
* An Amazon VPC with one AZ, one public subnet and one private subnet to run the EMR Serverless job
* An EMR Serverless application with EMR 6.9, private subnet and autoscaling up to 100 executors
* An AWS Step Function to trigger the EMR Serverless job and wait for completion
* An Amazon Event Bridge rule to trigger the job every 2 hours (disabled by default)

The job takes approximately 30 minutes to run.

#### Pre-requisites

* Customize the `log4j2.xml` in `docker` folder with the endpoint URL of the Opensearch ingestion for logs.
  The endpoint is generated by the `ingestor` stack and available as a CDK Output.

   * Use an Asynchronous appender encapsulating the custom appender to avoid any performance degradation:
   
```
<Appenders>
    ...
    <Async name="Async">
        <AppenderRef ref="Sparkobs"/>
    </Async>
    <SparkObs name="Sparkobs"
              endpoint="<LOGS_PIPELINE_URL>"
              region="<LOGS_PIPELINE_REGION>" batchSize="<OPENSEARCH_INGESTION_BATCHSIZE>" timeThreshold="<OPENSEARCH_INGESTION_THRESHOLD>"/>
    ...
</Appenders>
```

   * `batchSize` and `timeThreshold` can be omitted and will default to `100` and `10`. They can be adjusted to optimize the throughput of the collector with large jobs:
     * `batchSize` defines the number of logs to be collected and stored locally before sending them in batch to the backend.
     * `timeThreshold` defines the maximum time between batches sent to the backend. It ensures logs freshness: even if there is no new log, the previously generated log are flushed to the backend after this time.

   * Add the asynchronous appender ref in the Log4j2 root:

```
<Root level="info">
    <AppenderRef ref="Console"/>
    <AppenderRef ref="Async"/>
</Root>
```

* Build the collector library in `collector` folder and copy the jar file in `docker` folder so it's ready to be packaged in the EMR Serverless custom image:
    * Run in `<ROOT>/collector`
      ```
      sbt assembly
      ```
    * Copy the jar file
      ```
      cp <ROOT>/collector/target/scala-2.12/spark-observability-collector-assembly.jar <ROOT>/infra/emr-serverless/docker
      ```

#### CDK context Parameters

* `CollectorPolicyArn`: [REQUIRED] the IAM policy ARN with permissions to send metrics and logs to the ingestor stack.
* `MetricsPipelineUrl`: [REQUIRED] the URL of the Opensearch Ingestion pipeline for metrics. 
  Provided by the `ingestor` stack as a CDK parameter.
* `VpcID`: [OPTIONAL] the VPC ID where to deploy the EMR Serverless application.
  If no VPC ID is provided, the EMR Application is public.
* `SubnetsIDs`: [OPTIONAL] the comma separated list of subnets IDs to deploy the EMR Serverless application.
  If no subnets IDs are provided, it will use all private subnets with one per AZ from the provided VPC.

#### Manually trigger the TPCS DS benchmark

From the AWS Step Functions console, run the State Machine deployed by the CDK application.

#### Deploy your own Amazon EMR on EKS or Amazon EMR Serverless job

To deploy your own Spark application using EMR on EKS or EMR Serverless, you need to use [EMR custom Docker images](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/docker-custom-images-steps.html):

 * **Create a Log4j configuration that uses the collector custom appender.** 
  Add the following configuration to your `log4j2.xml`. The endpoint is generated by the `ingestor` stack and available as a CDK Output.
     * `batchSize` defines the number of logs to be collected and stored locally before sending them in batch to the backend. Default is `100`
     * `timeThreshold` defines the maximum time between batches sent to the backend. It ensures logs freshness: even if there is no new log, the previously generated log are flushed to the backend after this time. Default is `10`
   
```
<Appenders>
    ...
    <Async name="Async">
        <AppenderRef ref="Sparkobs"/>
    </Async>
    <SparkObs name="Sparkobs"
              endpoint="<OPENSEARCH_INGESTION_ENDPOINT>"
              region="<OPENSEARCH_INGESTION_REGION>" batchSize="<OPENSEARCH_INGESTION_BATCHSIZE>" timeThreshold="<OPENSEARCH_INGESTION_THRESHOLD>"/>
    ...
</Appenders>

<Root level="info">
    ...
    <AppenderRef ref="Async"/>
    ...
</Root>
```

 * Configure an EMR custom image by adding the `log4j2.xml` configuration file and the collector jar file. In your `Dockerfile`, add:

```
COPY log4j2.xml /etc/spark/conf/log4j2.xml
COPY spark-observability-collector-assembly-0.0.1.jar /usr/lib/spark-observability-collector.jar

RUN sed -i -e 's/^\(spark.driver.extraClassPath\).*$/&:\/usr\/lib\/spark-observability-collector.jar/g' /etc/spark/conf/spark-defaults.conf && \
    sed -i -e 's/^\(spark.executor.extraClassPath\).*$/&:\/usr\/lib\/spark-observability-collector.jar/g' /etc/spark/conf/spark-defaults.conf && \
    rm -f /etc/spark/conf/log4j2.properties
```
 * Build the collector library and copy the jar file in the same folder as the Dockerfile

    * Run in `<ROOT>/collector`
      ```
      sbt assembly
      ```
    * Copy the jar file
      ```
      cp <ROOT>/collector/target/scala-2.12/spark-observability-collector-assembly.jar <CUSTOM_EMR_DOCKER_IMAGE_PATH>/
      ```

 * Build the Docker image and upload it in ECR following the EMR documentation instructions
 * Attach the ingestor IAM policy to your execution role. The ingestor policy ARN is provided by the `ingestor` stack and available as a CDK Output
 * Submit the Spark job with collector metrics parameters 

```
--conf spark.extraListeners=com.amazonaws.sparkobservability.CustomMetricsListener 
--conf spark.metrics.region=<METRICS_PIPELINE_REGION>
--conf spark.metrics.endpoint=<METRICS_PIPELINE_URL> 
--conf spark.metrics.batchSize=100 
--conf spark.metrics.timeThreshold=10
```

## Analyze data in Opensearch Dashboards

1. Go to the Opensearch Dashboard. The URL is provided by the `backend` stack as a CDK parameter. 
The `admin` username and password are stored in AWS Secret Manager.
1. Dashboards are provisioned by the CDK Stack. You cna start analyzing logs and metrics.