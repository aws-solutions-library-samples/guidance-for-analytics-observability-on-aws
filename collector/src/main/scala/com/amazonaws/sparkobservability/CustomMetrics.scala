package com.amazonaws.sparkobservability

import scala.collection.JavaConverters._

sealed abstract class CustomMetrics(val appName: String, val appId: String, val jobId: String, val metricsType: String) extends Product {

  def toMap() = {
    this.getClass.getDeclaredFields.map(_.getName).zip(this.productIterator.to).toMap.asJava
  }
}

case class CustomTaskMetrics(
                            override val appName: String,
                            override val appId: String,
                            override val jobId: String,
                            stageId: Integer,
                            stageAttemptId: Integer,
                            taskId: String,
                            executorId: String,
                            partitionId: Int,
                            inputBytesRead: Double,
                            inputRecordsRead: Double,
                            runTime: Double,
                            executorCpuTime: Double,
                            peakExecutionMemory: Double,
                            outputRecordsWritten: Double,
                            outputBytesWritten: Double,
                            shuffleRecordsRead: Double,
                            shuffleBytesRead: Double,
                            shuffleRecordsWritten: Double,
                            shuffleBytesWritten: Double
                            ) extends CustomMetrics(appName, appId, jobId, metricsType="taskMetrics")

case class CustomLightTaskMetrics(
                            override val appName: String,
                            override val appId: String,
                            override val jobId: String,
                            stageId: Integer,
                            taskId: String,
                            inputBytesRead: Double,
                            shuffleBytesRead: Double
                            ) extends CustomMetrics(appName, appId, jobId, metricsType="lightTaskMetrics")

case class CustomStageAggMetrics(
                             override val appName: String,
                             override val appId: String,
                             override val jobId: String,
                             stageId: Integer,
                             inputBytesReadSkewness: Double,
                             maxInputBytesRead: Double,
                             shuffleBytesReadSkewness: Double,
                             maxShuffleBytesRead: Double
                            ) extends CustomMetrics(appName, appId, jobId, metricsType="stageAggMetrics")