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
```
./bin/spark-shell 
    --conf spark.extraListeners=com.amazonaws.sparkobservability.CustomMetricsListener
    --conf spark.metrics.region=<REGION>
    --conf spark.metrics.endpoint=<OPENSEARCH_PIPELINE_ENDPOINT>
    --driver-class-path <LOCAL_PATH>/spark-observability/collector/target/scala-2.12/spark-observability-collector-assembly-0.0.1.jar
```

3. Execute a simple spark command to see the output of the custom listener
```
spark.read.text("<LOCAL_PATH>/spark-observabiity/collector/README.md").count
```

## Use the Spark plugin to run arbitrary tasks

The Spark plugin is useful to execute arbitrary code when the Spark driver or executors are initialized. **We don't use the Spark plugin for now.**

3. Run spark-shell loading the plugin
```
./bin/spark-shell --conf spark.plugins=com.amazonaws.sparkobservability.CustomLogsPlugin --driver-class-path <LOCAL_PATH>/spark-observability/collector/target/scala-2.12/spark-observability-collector-assembly-0.0.1.jar
```


# Use the custom appender to export driver and executor logs

The custom appender is used to send logs to the observability client. It natively integrates with log4j2.

1. Configure the `log4j2.xml` or `log4j2.properties` file

2. Run a spark-shell loading the custom appender
```
<SPARK_HOME>/bin/spark-shell --conf 'spark.driver.extraJavaOptions=-Dlog4j.configurationFile=<LOCAL_PATH>/spark-observability/collector/log4j2.xml -Dlog4j2.contextSelector=org.apache.logging.log4j.core.async.AsyncLoggerContextSelector' --driver-class-path <LOCAL_PATH>/spark-observability/collector/target/scala-2.12/spark-observability-collector-assembly-0.0.1.jar 
```
3. You can enable log4j2 debugging with `-Dlog4j.debug=true` as a Java option

4. Run Spark code
```
 spark.read.text("./collector/README.md").count
```

# test the Spark observability collector in EMR Serverless

1. Create an EMR Serverless application

```
{
  "application": {
    "name": "spark-obs",
    "releaseLabel": "emr-6.10.0",
    "type": "Spark",
    "autoStartConfiguration": {
      "enabled": true
    },
    "autoStopConfiguration": {
      "enabled": true,
      "idleTimeoutMinutes": 15
    },
    "networkConfiguration": {
      "subnetIds": [
        "<SUBNET1_ID>",
        "<SUBNET2_ID>"
      ],
      "securityGroupIds": [
        "<SG_GROUP>"
      ]
    },
    "architecture": "X86_64",
    "imageConfiguration": {
      "imageUri": "<ECR_CUSTOM_IMAGE>"
    }
  }
}
```

2. Run a job

```
{
  "jobRun": {
    "applicationId": "<APPLICATION_ID>",
    "executionRole": "<EXECUTION_ROLE_ARN>",
    "configurationOverrides": {
      "monitoringConfiguration": {
        "s3MonitoringConfiguration": {
          "logUri": "s3://spark-observability-099713751195/logs/"
        },
        "managedPersistenceMonitoringConfiguration": {
          "enabled": true
        }
      }
    },
    "jobDriver": {
      "sparkSubmit": {
        "entryPoint": "s3://spark-observability-099713751195/ge_profile.py",
        "entryPointArguments": [
          "s3://spark-observability-099713751195/tmp/ge-profile"
        ],
        "sparkSubmitParameters": "--conf spark.driver.extraJavaOptions=-Dlog4j2.contextSelector=org.apache.logging.log4j.core.async.AsyncLoggerContextSelector --conf spark.jars=s3://spark-observability-099713751195/spark-observability-collector-assembly-0.0.1.jar --conf spark.extraListeners=com.amazonaws.sparkobservability.CustomMetricsListener --conf spark.obs.region=us-west-2 --conf spark.obs.endpoint=https://spark-obs-metrics-6shkttignlqeh4waglhefoy6ay.us-west-2.osis.amazonaws.com/ingest --conf spark.driver.cores=2 --conf spark.driver.memory=4g --conf spark.executor.cores=2 --conf spark.executor.memory=8g --conf spark.executor.instances=10 --conf spark.archives=s3://spark-observability-099713751195/pyspark_ge.tar.gz#environment --conf spark.emr-serverless.driverEnv.PYSPARK_DRIVER_PYTHON=./environment/bin/python --conf spark.emr-serverless.driverEnv.PYSPARK_PYTHON=./environment/bin/python --conf spark.emr-serverless.executorEnv.PYSPARK_PYTHON=./environment/bin/python"
      }
    }
  }
}
```