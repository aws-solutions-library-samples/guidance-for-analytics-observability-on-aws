# AWS Spark Observability solution

The AWS Tooling to analyze Spark jobs

1. Build the `collector` jar

2. Deploy the `infra` CDK stack

2. Deploy the `example/emr-serverless` CDK stack 


### Limitations

 * Single account only
 * Infrastructure deployed in public mode
 * A NAT gateway is required to access the Observability infrastructure