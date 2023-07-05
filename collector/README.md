# Test the Spark observability collector locally

The collector is composed of:
- A Spark customer listener to collect Spark metrics from the driver
- A custom log4j2 appender to collect Spark executors and driver logs
- A custom Spark plugin to execute arbitrary tasks when starting executors and driver  
- A custom Opensearch ingestion client to send metrics and logs to an Opensearch ingestion

## Pre-requisite

1. Package the Spark observability collector

```
sbt assembly
```

## Use the Spark custom listener to export metrics

2. Run spark-shell loading the custom listener
```shell
./bin/spark-shell \
    --conf spark.extraListeners=com.amazonaws.sparkobservability.CustomMetricsListener \
    --conf spark.metrics.region=<REGION> \
    --conf spark.metrics.endpoint=<OPENSEARCH_PIPELINE_ENDPOINT> \
    --driver-class-path <LOCAL_PATH>/spark-observability/collector/target/scala-2.12/spark-observability-collector-assembly-0.0.1.jar
```

3. Execute a simple spark command to see the output of the custom listener
```
spark.read.text("<LOCAL_PATH>/spark-observabiity/collector/README.md").count
```

## Use the Spark plugin to run arbitrary tasks

The Spark plugin is useful to execute arbitrary code when the Spark driver or executors are initialized. **We don't use the Spark plugin for now.**

3. Run spark-shell loading the plugin
```shell
./bin/spark-shell \
    --conf spark.plugins=com.amazonaws.sparkobservability.CustomLogsPlugin \
    --driver-class-path <LOCAL_PATH>/spark-observability/collector/target/scala-2.12/spark-observability-collector-assembly-0.0.1.jar
```


# Use the custom appender to export driver and executor logs

The custom appender is used to send logs to the observability client. It natively integrates with log4j2.

1. Configure the `log4j2.xml` or `log4j2.properties` file

2. Run a spark-shell loading the custom appender
```shell
./bin/spark-shell \
    --conf spark.driver.extraJavaOptions='-Dlog4j.configurationFile=<LOCAL_PATH>/spark-observability/collector/log4j2.xml -Dlog4j2.contextSelector=org.apache.logging.log4j.core.async.AsyncLoggerContextSelector' \
    --driver-class-path <LOCAL_PATH>/spark-observability/collector/target/scala-2.12/spark-observability-collector-assembly-0.0.1.jar 
```
3. You can enable log4j2 debugging with `-Dlog4j.debug=true` as a Java option

4. Run Spark code
```python
 spark.read.text("./collector/README.md").count
```

# test the Spark observability collector in EMR Serverless

 Refer to the `examples` folder for creating an EMR Serverless application and submitting a TPCDS job with the Spark Observability tooling