package com.amazonaws.sparkobservability

import org.apache.spark.scheduler.{SparkListener, SparkListenerJobStart, SparkListenerStageCompleted, SparkListenerTaskEnd}
import org.slf4j.LoggerFactory
import scala.collection.mutable.HashMap

import java.util

class CustomMetricsListener extends SparkListener {

  private val logger = LoggerFactory.getLogger(this.getClass.getName)
  private val client = new ObservabilityClient(Utils.getObservabilityEndpoint(), Utils.getAwsRegion())
  private val stageToJobMapping = HashMap.empty[Int, String]

  override def onJobStart(jobStart: SparkListenerJobStart) {
    logger.info(s"Job started with ${jobStart.stageInfos.size} stages: $jobStart")
    // Map each stageId to the jobId
    for (stageId <- jobStart.stageIds) {
      stageToJobMapping += (stageId -> jobStart.jobId.toString)
    }
  }

  override def onStageCompleted(stageCompleted: SparkListenerStageCompleted): Unit = {
    logger.info(s"Stage ${stageCompleted.stageInfo.stageId} completed with ${stageCompleted.stageInfo.numTasks} tasks.")
  }

  override def onTaskEnd(taskEnded: SparkListenerTaskEnd){

    val metrics = collectTaskCustomMetrics(taskEnded)

    client.send(metrics)
    logger.info(s"Metrics collected: ${metrics}")
  }

  def collectTaskCustomMetrics(taskEnded: SparkListenerTaskEnd): CustomTaskMetrics = {
    
    CustomTaskMetrics(
      appName = Utils.getAppName(),
      appId = Utils.getAppId(),
      jobId = stageToJobMapping(taskEnded.stageId),
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
