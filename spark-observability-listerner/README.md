# Test the custom spark listener

1. Package the JAR
```
sbt package
```

2. Run spark-shell loading the custom listener
```
./bin/spark-shell --conf spark.extraListeners=com.amazonaws.sparkobservabilitylistener.CustomSparkListener --driver-class-path <LOCAL_PATH>/spark-observability/spark-observability-listerner/target/scala-2.12/spark-observability-listener_2.12-0.1.jar
```

3. Execute a simple spark command to see the output of the custom listener
```
spark.read.text("<LOCAL_PATH>/spark-observabiity/README.md").count
```

# Add http appended to log4j2

1. A log4j2 properties file is provided as an example

2. Testing the HTTP appender with local docker opensearch instance requires to add the self-signed certificate to the java keystore. 
Follow this [blog](https://blog.packagecloud.io/solve-unable-to-find-valid-certification-path-to-requested-target/) to do that

2. Changing the `log4j2.properties` file doesn't work. Current bug in Spark 3.3.0? Instead, copy the file in `$SPARK_HOME/conf`

```
# Doesn't work
./bin/spark-shell --conf 'spark.driver.extraJavaOptions=-Dlog4j.configuration=<LOCAL_PATH>/spark-observability/log4j2.properties -Dlog4j.debug=true'
```

