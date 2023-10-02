# Spark observability collector

The Spark observability collector is the component responsible for collecting Spark logs and metrics in near real-time, 
directly from the Spark application and sending them to the [Spark Observability infrastructure](../infra). 
It's a Scala based component available as a jar file that is compatible with any Apache Spark runtime as long as the Jar file is on the classpath.

The collector is composed of:
- A Spark customer listener to collect Spark metrics from the driver
- A custom Log4j2 appender to collect Spark executors and driver logs
- A custom Spark plugin to execute arbitrary tasks when starting executors and driver (currently not used)
- A custom Opensearch Ingestion client to send metrics and logs to an Opensearch Ingestion pipeline


## Getting started 

### Pre-requisite

A Spark Observability infrastructure deployed in AWS. For local testing, use the docker compose available [here](../infra/dev/compose.yml)

### Build the Spark Observability collector

Build the Spark observability collector using SBT

```
sbt assembly
```

### Configure Log4j2

Add the custom appender to the Spark log4j2 configuration. Use a [`log4j2.xml`](examples/log4j2.xml) file or [`log42.properties`](examples/log4j2.properties). 
1. Use an Asynchronous appender encapsulating the custom appender to avoid any performance degradation:
   
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
```

2. Add the asynchronous appender ref in the Log4j2 root:

```
<Root level="info">
    <AppenderRef ref="Console"/>
    <AppenderRef ref="Async"/>
</Root>
```

3. Configure the appender with values from the Spark Observability infrastructure deployed in AWS. For local testing, configure:
 * `http://localhost:2021/ingest` as the endpoint
 * Any region value
 * `batchSize` and `timeThreshold` can be omitted and will default to `100` and `10`

### Package and submit a Spark job

#### Spark on EKS, EMR Serverless, EMR on EKS

1. Build a custom docker image like described in the [EMR Serverless example](../examples/emr-serverless/docker/Dockerfile) dockerfile. 
   The Docker image will:
    1. Add the Collector assembly jar file into the Spark runtime as a dependency. 
       The Jar file cannot be loaded from Amazon S3 via `--conf spark.jars` because it's required from the JVM start before the Spark context is created.
    2. Configure the driver and executors classpath to include the Collector jar
    3. Add the `log4j2.xml` configuration file into `/etc/spark/conf` so it's automatically loaded by Spark
   
2. Submit the job with the following Spark configuration
```shell
    --conf spark.extraListeners=com.amazonaws.sparkobservability.CustomMetricsListener \
    --conf spark.metrics.region=<REGION> \
    --conf spark.metrics.endpoint=<OPENSEARCH_PIPELINE_ENDPOINT> \
    --conf spark.metrics.batchSize=<BATCH_SIZE> \
    --conf spark.metrics.timeThreshold=<TIME_THRESHOLD>
```

#### EMR on EC2

COMING SOON
   
#### Local testing

For local testing, use the following Spark shell command:
```
./bin/spark-shell \
    --conf spark.driver.extraJavaOptions='-Dlog4j.configurationFile=<LOCAL_PATH>/spark-observability/collector/log4j2.xml -Dlog4j.debug=true' \
    --conf spark.extraListeners=com.amazonaws.sparkobservability.CustomMetricsListener \
    --conf spark.metrics.region=us-east-1 \
    --conf spark.metrics.endpoint=http://localhost:2021/ingest \
    --driver-class-path <LOCAL_PATH>/spark-observability/collector/target/scala-2.12/spark-observability-collector-assembly-0.0.1.jar
```
