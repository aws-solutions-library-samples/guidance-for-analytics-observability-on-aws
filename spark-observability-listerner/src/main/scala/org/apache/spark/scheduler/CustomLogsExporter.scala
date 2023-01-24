package org.apache.spark.scheduler
import org.apache.hadoop.conf.Configuration
import org.apache.spark.SparkConf
import org.apache.spark.internal.Logging

import java.net.URI


class CustomLogsExporter(
                          appId: String,
                          appAttemptId : Option[String],
                          logBaseDir: URI,
                          sparkConf: SparkConf,
                          hadoopConf: Configuration) extends Logging {

}
