package com.amazonaws.sparkobservability

import org.apache.log4j.{LogManager, Logger}
import org.apache.spark.SparkConf
import org.apache.spark.sql.SparkSession


object sparksql {
  def main(args: Array[String]): Unit = {

  //  val spark = new SparkContext(conf)
    val spark = SparkSession.builder()
      .appName("Spark SQL - new")
      .master("local[2]")
      .config("spark.metrics.endpoint", "http://localhost:2021/ingest")
      .config("spark.metrics.region", "test")
      .config("spark.plugins", "com.amazonaws.sparkobservability.ObservabilityPlugin")
      .getOrCreate()


    val jsonFilePath = "C:\\\\dev\\\\analytics-obs\\\\spark-observability\\\\collector\\\\src\\\\main\\\\scala\\\\com\\\\amazonaws\\\\sparkobservability\\\\sample.csv"  // replace with your file path
    val df = spark.read
      .option("header", "true") // Reading the headers
      .option("inferSchema", "true") // Inferring the schema of the CSV file
      .csv(jsonFilePath)
    // Show the data
    df.show()

    // Register the DataFrame as a SQL temporary view
    df.createOrReplaceTempView("people")

    // Perform a SQL query
    val sqlDF = spark.sql("SELECT * FROM people WHERE age > 30")

    spark.sparkContext.setJobGroup("test instrumentation", "Run Q1")
    // Perform a group by operation and count for each group
    val resultDF = sqlDF.groupBy("age").count()
    // Show the results of the SQL query
    resultDF.show()

  //  Thread.sleep(1000000000)
  //  print("hello")

  }
}

