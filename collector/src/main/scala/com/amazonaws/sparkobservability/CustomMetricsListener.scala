package com.amazonaws.sparkobservability

import org.apache.spark.scheduler.{SparkListener, SparkListenerApplicationEnd, SparkListenerJobEnd, SparkListenerJobStart, SparkListenerStageCompleted, SparkListenerTaskEnd}
import org.slf4j.LoggerFactory

import scala.collection.mutable.{HashMap, ListBuffer}
import scala.math

class CustomMetricsListener extends SparkListener {

  private val logger = LoggerFactory.getLogger(this.getClass.getName)
  private val client = new ObservabilityClient[CustomMetrics](Utils.getObservabilityEndpoint(), Utils.getAwsRegion(), Utils.getBatchSize(), Utils.getTimeThreshold())
  private val stageToJobMapping = HashMap.empty[Int, String]
  private val taskMetricsBuffer = ListBuffer[CustomLightTaskMetrics]()

  override def onApplicationEnd(applicationEnd: SparkListenerApplicationEnd): Unit = {
    println("shutdown hook! Flushing observability client...")
    client.flushEvents()
  }
  override def onJobStart(jobStart: SparkListenerJobStart) {
    logger.debug(s"Job started with ${jobStart.stageInfos.size} stages: $jobStart")
    // Map each stageId to the jobId
    for (stageId <- jobStart.stageIds) {
      stageToJobMapping += (stageId -> jobStart.jobId.toString)
    }
  }

  override def onJobEnd(jobEnd: SparkListenerJobEnd): Unit = {
    client.flushEvents()
  }

  override def onStageCompleted(stageCompleted: SparkListenerStageCompleted): Unit = {
    val metrics = collectStageCustomMetrics(stageCompleted)
    logger.debug(s"Stage metrics collected: ${metrics}")
    client.add(metrics)
    stageToJobMapping.remove(stageCompleted.stageInfo.stageId)
    taskMetricsBuffer.clear()
  }

  override def onTaskEnd(taskEnded: SparkListenerTaskEnd){
    val metrics = collectTaskCustomMetrics(taskEnded)
    client.add(metrics)
    logger.debug(s"Task metrics collected: ${metrics}")
    taskMetricsBuffer += CustomLightTaskMetrics(
      metrics.appName,
      metrics.appId,
      metrics.jobId,
      metrics.stageId,
      metrics.taskId,
      metrics.inputBytesRead,
      metrics.shuffleBytesRead
    )
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

  def collectStageCustomMetrics(stageCompleted: SparkListenerStageCompleted): CustomStageAggMetrics = {
    val length = taskMetricsBuffer.length

    // Process the relative distance of tasks for their inputBytesRead
    logger.debug("tasksMetricsBuffer length  "+ taskMetricsBuffer.length + " for stage ID " + stageCompleted.stageInfo.stageId)
    val inputBytesRead = taskMetricsBuffer.map(_.inputBytesRead)
    val avgInputBytesRead = inputBytesRead.reduce(_ + _) / length
    logger.debug("avgInputBytesRead  "+ avgInputBytesRead + " for stage ID " + stageCompleted.stageInfo.stageId)
    val maxInputBytesRead = inputBytesRead.max
    val rangeInputBytesRead = maxInputBytesRead - inputBytesRead.min match {
      case 0 => 1
      case x => x
    }
    logger.debug("rangeInputBytesRead  "+ rangeInputBytesRead + " for stage ID " + stageCompleted.stageInfo.stageId)
    val maxInputRelDistance = inputBytesRead.map(x => (x - avgInputBytesRead).abs / rangeInputBytesRead).max
    logger.debug("maxInputRelDistance  "+ maxInputRelDistance + " for stage ID " + stageCompleted.stageInfo.stageId)

    // Process the relative distance of tasks for their shuffleBytesRead
    val shuffleBytesRead = taskMetricsBuffer.map(_.shuffleBytesRead)
    val avgShuffleBytesRead = shuffleBytesRead.reduce(_ + _) / length
    logger.debug("avgShuffleBytesRead  "+ avgShuffleBytesRead + " for stage ID " + stageCompleted.stageInfo.stageId)
    val maxShuffleBytesRead = shuffleBytesRead.max
    val rangeShuffleBytesRead = maxShuffleBytesRead - shuffleBytesRead.min match {
      case 0 => 1
      case x => x
    }
    logger.debug("rangeShuffleBytesRead  "+ rangeShuffleBytesRead + " for stage ID " + stageCompleted.stageInfo.stageId)
    val maxShuffleRelDistance = shuffleBytesRead.map(x => (x - avgShuffleBytesRead).abs / rangeShuffleBytesRead).max
    logger.debug("maxShuffleRelDistance  "+ maxShuffleRelDistance + " for stage ID " + stageCompleted.stageInfo.stageId)

    val metric = taskMetricsBuffer.head
    CustomStageAggMetrics(
      metric.appName,
      metric.appId,
      metric.jobId,
      metric.stageId,
      maxInputRelDistance,
      maxInputBytesRead,
      maxShuffleRelDistance,
      maxShuffleBytesRead
    )
  }
}
