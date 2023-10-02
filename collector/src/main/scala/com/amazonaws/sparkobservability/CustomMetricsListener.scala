package com.amazonaws.sparkobservability

import org.apache.spark.scheduler._
import org.slf4j.LoggerFactory

import java.time.Instant
import scala.collection.mutable.{HashMap, ListBuffer}

/**
 * A custom Spark listener to collect metrics and send to an observability client.
 */
class CustomMetricsListener extends SparkListener {

  /**
   * The logger to log debug information.
   */
  private val logger = LoggerFactory.getLogger(this.getClass.getName)

  /**
   * The client to send metrics to the observability solution.
   */
  private val client = new ObservabilityClient[CustomMetrics](Utils.getObservabilityEndpoint(), Utils.getAwsRegion(), Utils.getBatchSize(), Utils.getTimeThreshold())

  /**
   * A map to keep track of the mapping between stage ID and job ID. Used to enrich metrics.
   */
  private val stageToJobMapping = HashMap.empty[Int, String]

  /**
   * A buffer to collect task metrics within a stage and aggregate them per stage
   */
  private val taskMetricsBuffer = ListBuffer[CustomLightTaskMetrics]()

  /**
   * Listen to application end and then flush any pending metrics to the observability client.
   */
  override def onApplicationEnd(applicationEnd: SparkListenerApplicationEnd): Unit = {
    println("shutdown hook! Flushing observability client...")
    client.flushEvents()
  }

  /**
   * Listen to application start, and then set the last flush time to now.
   * Avoid the situation where Spark takes more time than the batchTime and then the ObservabilityClient sends the
   * first metric alone.
   */
  override def onApplicationStart(appStart: SparkListenerApplicationStart) {
    logger.debug(s"App started in ${appStart.time} seconds... Initializing lastFlush now")
    client.setLastFlush(Instant.now)
  }

  /**
   * Listen to job start, and then map each stage ID to the corresponding job ID.
   */
  override def onJobStart(jobStart: SparkListenerJobStart) {
    logger.debug(s"Job started with ${jobStart.stageInfos.size} stages: $jobStart")
    // Map each stageId to the jobId
    for (stageId <- jobStart.stageIds) {
      stageToJobMapping += (stageId -> jobStart.jobId.toString)
    }
  }

  /**
   * Listen to job end, and then flush any pending metrics to the observability client.
   */
  override def onJobEnd(jobEnd: SparkListenerJobEnd): Unit = {
    client.flushEvents()
  }

  /**
   * Listen to stage completion, process stage aggregated metrics and then send them to the observability client.
   */
  override def onStageCompleted(stageCompleted: SparkListenerStageCompleted): Unit = {
    val metrics = collectStageCustomMetrics(stageCompleted)
    logger.debug(s"Stage metrics collected: ${metrics}")
    client.add(metrics)
    stageToJobMapping.remove(stageCompleted.stageInfo.stageId)
    taskMetricsBuffer.clear()
  }

  /**
   * Listen to task end, collect tasks metrics, send them to the observability client and create light task metrics
   * used to process stage level aggregation.
   */
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

  /**
   * Collect metrics from completed tasks.
   * @param taskEnded The Spark metrics related to the completed task
   * @return The CustomTaskMetrics for the current task
   */
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

  /**
   * Collect stage level aggregated metrics when a stage completes.
   * The method collects all the task metrics from the stage and perform the following aggregations:
   *   * max relative distance for input bytes read
   *   * max input bytes read
   *   * max relative distance for shuffle bytes read
   *   * max shuffle bytes read
   * @param stageCompleted The Spark metrics related to the completed stage
   * @return The CustomStageAggMetrics for the current stage
   */
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
