package com.amazonaws.sparkobservability

trait CustomMetrics {
  val appName: String
  val appId: String
  val jobId: String
}

case class CustomTaskMetrics(
                            appName: String,
                            appId: String,
                            jobId: String,
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
                            ) extends CustomMetrics

case class CustomStageMetrics(
                             appName: String,
                             appId: String,
                             jobId: String,
                             stageId: Integer,
                             attemptId: String,
                             numTasks: Integer
                            ) extends CustomMetrics