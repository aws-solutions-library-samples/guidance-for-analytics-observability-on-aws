package org.apache.spark.scheduler

import org.apache.hadoop.conf.Configuration
import org.apache.spark.SparkConf
import org.apache.spark.deploy.SparkHadoopUtil
import org.apache.spark.deploy.history.EventLogFileWriter

import java.net.URI

class CustomLogsListener( var appId: String,
                          var appAttemptId : Option[String],
                          var logBaseDir: URI,
                          var sparkConf: SparkConf,
                          var hadoopConf: Configuration)
  extends EventLoggingListener( appId, appAttemptId, logBaseDir, sparkConf, hadoopConf) {

  override private[scheduler] val logWriter: EventLogFileWriter =
    EventLogFileWriter(appId, appAttemptId, logBaseDir, sparkConf, hadoopConf)
}
