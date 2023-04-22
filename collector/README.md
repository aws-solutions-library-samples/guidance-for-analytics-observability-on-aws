# Test the custom spark listener

The custom spark listener is used to collect metrics from the Spark driver. 
The custom listener is using the observability client to send data to OSI.

1. Package the JAR
```
sbt assembly
```

2. Run spark-shell loading the custom listener
```
./bin/spark-shell --conf spark.extraListeners=com.amazonaws.sparkobservability.CustomMetricsListener --driver-class-path <LOCAL_PATH>/spark-observability/collector/target/scala-2.12/spark-observability-collector-assembly-0.0.1.jar
```

3. Execute a simple spark command to see the output of the custom listener
```
spark.read.text("<LOCAL_PATH>/spark-observabiity/collector/README.md").count
```

# Test the Spark plugin

The Spark plugin is useful to execute arbitrary code when the Spark driver or executors are initialized. **We don't use the Spark plugin for now.**

1. Package the JAR
```
sbt package
```

2. Run spark-shell loading the plugin
```
./bin/spark-shell --conf spark.plugins=com.amazonaws.sparkobservability.CustomLogsPlugin --driver-class-path <LOCAL_PATH>/spark-observability/collector/target/scala-2.12/spark-observability-collector-assembly-0.0.1.jar
```


# Test the custom appender

The custom appender is used to send logs to the observability client. It natively integrates with log4j.

```
<SPARK_HOME>/bin/spark-shell --conf 'spark.driver.extraJavaOptions=-Dlog4j.configurationFile=<LOCAL_PATH>/spark-observability/collector/log4j2.xml -Dlog4j.debug=true' --driver-class-path <LOCAL_PATH>/spark-observability/collector/target/scala-2.12/spark-observability-collector-assembly-0.0.1.jar 
```

Run Spark code
```
 spark.read.text("./collector/README.md").count
```
