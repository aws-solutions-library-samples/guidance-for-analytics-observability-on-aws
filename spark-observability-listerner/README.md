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