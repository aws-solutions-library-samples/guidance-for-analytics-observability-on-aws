package com.amazonaws.sparkobservability

import org.apache.spark.scheduler.{SparkListener, SparkListenerJobStart, SparkListenerStageCompleted, SparkListenerTaskEnd}
import org.slf4j.LoggerFactory

import scala.collection.mutable.Map

class CustomMetricsListener extends SparkListener {

  private val logger = LoggerFactory.getLogger(this.getClass.getName)

  override def onJobStart(jobStart: SparkListenerJobStart) {
    logger.info(s"Job started with ${jobStart.stageInfos.size} stages: $jobStart")
  }

  override def onStageCompleted(stageCompleted: SparkListenerStageCompleted): Unit = {
    logger.info(s"Stage ${stageCompleted.stageInfo.stageId} completed with ${stageCompleted.stageInfo.numTasks} tasks.")
  }

  override def onTaskEnd(taskEnded: SparkListenerTaskEnd){
    val metrics = collectTaskCustomMetrics(taskEnded)
    logger.info(s"Metrics collected: ${metrics}")
  }

  def collectTaskCustomMetrics(taskEnded: SparkListenerTaskEnd): CustomTaskMetrics = {
    
    CustomTaskMetrics(
      appName = Utils.getAppName(),
      appId = Utils.getAppId(),
      //TODO find a way to collect the jobID
      jobId = "1",
      stageId = taskEnded.stageId,
      stageAttemptId = taskEnded.stageAttemptId,
      taskId = taskEnded.taskInfo.id,
      executorId = taskEnded.taskInfo.executorId,
      partitionId = taskEnded.taskInfo.partitionId,
      inputBytesRead = taskEnded.taskMetrics.inputMetrics.bytesRead,
      inputRecordsRead = taskEnded.taskMetrics.inputMetrics.recordsRead,
      runTime = taskEnded.taskMetrics.executorRunTime,
      executorCpuTime = taskEnded.taskMetrics.executorCpuTime,
      peakExecutionMemory = taskEnded.taskMetrics.peakExecutionMemory,
      outputRecordsWritten = taskEnded.taskMetrics.outputMetrics.recordsWritten,
      outputBytesWritten = taskEnded.taskMetrics.outputMetrics.bytesWritten,
      shuffleRecordsRead = taskEnded.taskMetrics.shuffleReadMetrics.recordsRead,
      shuffleBytesRead = taskEnded.taskMetrics.shuffleReadMetrics.totalBytesRead,
      shuffleRecordsWritten = taskEnded.taskMetrics.shuffleWriteMetrics.recordsWritten,
      shuffleBytesWritten = taskEnded.taskMetrics.shuffleWriteMetrics.bytesWritten
    )
  }
}
