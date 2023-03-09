package com.amazonaws.sparkobservability

import scala.collection.JavaConverters._

sealed abstract class CustomMetrics(val appName: String, val appId: String, val jobId: String) extends Product {

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
                            ) extends CustomMetrics(appName, appId, jobId)

case class CustomStageMetrics(
                             override val appName: String,
                             override val appId: String,
                             override val jobId: String,
                             stageId: Integer,
                             attemptId: String,
                             numTasks: Integer
                            ) extends CustomMetrics(appName, appId, jobId)