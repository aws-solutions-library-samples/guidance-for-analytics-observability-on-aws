# Test the custom spark listener

1. Package the JAR
```
sbt package
```

2. Run spark-shell loading the custom listener
```
./bin/spark-shell --conf spark.extraListeners=com.amazonaws.sparkobservabilitylistener.CustomSparkListener --driver-class-path <LOCAL_PATH>/spark-observability/spark-observability-listener/target/scala-2.12/spark-observability-listener_2.12-0.1.jar
```

3. Execute a simple spark command to see the output of the custom listener
```
spark.read.text("<LOCAL_PATH>/spark-observabiity/README.md").count
```

# Add http appended to log4j2

1. A log4j2 xml config file is provided as an example

2. Testing the HTTP appender with local docker opensearch instance requires to add the self-signed certificate to the java keystore. 
Follow this [blog](https://blog.packagecloud.io/solve-unable-to-find-valid-certification-path-to-requested-target/) to do that
   
3. Run the docker stack (opensearch and opensearch dashboard) using

```
docker compose up
```

2. Change the log4j2 configuration with

```
./bin/spark-shell --conf 'spark.driver.extraJavaOptions=-Dlog4j.configurationFile=<LOCAL_PATH>/spark-observability/spark-observability-listener/log4j2.xml -Dlog4j.debug=true'
```

4. Open the opensearch dashboard, create an index mapping on `test*` and you should see logs in `discover`

# Test the Spark plugin

1. Package the JAR
```
sbt package
```

2. Run spark-shell loading the plugin
```
./bin/spark-shell --conf spark.plugins=com.amazonaws.sparkobservability.CustomLogsPlugin --driver-class-path <LOCAL_PATH>/spark-observability/spark-observability-listener/target/scala-2.12/custom-spark-listener_2.12-0.0.1.jar
```


# Test the custom appender


```
./bin/spark-shell --conf 'spark.driver.extraJavaOptions=-Dlog4j.configurationFile=<LOCAL_PATH>/spark-observability/spark-observability-listener/log4j2.xml -Dlog4j.debug=true' --driver-class-path <LOCAL_PATH>/spark-observability/spark-observability-listener/target/scala-2.12/custom-spark-listener_2.12-0.0.1.jar
```