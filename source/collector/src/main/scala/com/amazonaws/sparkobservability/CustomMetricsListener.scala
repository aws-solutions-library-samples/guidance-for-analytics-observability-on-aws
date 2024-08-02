// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

package com.amazonaws.sparkobservability

import org.apache.spark.SparkContext
import org.apache.spark.scheduler._
import org.apache.spark.sql.execution.ui.{SQLAppStatusListener, SQLAppStatusStore, SQLExecutionUIData, SparkPlanGraphNode}
import org.apache.spark.util.kvstore.KVStore
import org.slf4j.LoggerFactory

import java.time.Instant
import scala.collection.mutable.{HashMap, ListBuffer}
import org.joda.time.DateTime

/**
 * A custom Spark listener to collect metrics and send to an observability client.
 */
class CustomMetricsListener(context: SparkContext, sqlListener: () => Option[SQLAppStatusListener]) extends SparkListener {

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

  private var maxSqlOffset: Int = 0

  /**
   * Listen to application end and then flush any pending metrics to the observability client.
   */
  override def onApplicationEnd(applicationEnd: SparkListenerApplicationEnd): Unit = {
    reportNewSqlMetrics()
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
      metrics.shuffleBytesRead)
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
      shuffleBytesWritten = taskEnded.taskMetrics.shuffleWriteMetrics.bytesWritten)
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
      maxShuffleBytesRead)
  }


  private def reportNewSqlMetrics(): Unit = {
    val sqlStore = getSqlStore()
    val executions = getExecutions(sqlStore)
    val allMetrics = getAllMetrics(sqlStore, executions)

    processNodes(sqlStore, executions, allMetrics)
    processEdges(sqlStore, executions)
    saveExecutions(executions)
  }

  private def getSqlStore(): SQLAppStatusStore = {
    val listener = this.sqlListener()
    val statusStore = getStatusStore()
    val kvStore = getKVStore(statusStore)
    new SQLAppStatusStore(kvStore, listener)
  }

  private def getStatusStore(): Any = {
    context.getClass.getMethod("statusStore").invoke(context)
  }

  private def getKVStore(statusStore: Any): KVStore = {
    val storeField = statusStore.getClass.getDeclaredField("store")
    storeField.setAccessible(true)
    storeField.get(statusStore).asInstanceOf[KVStore]
  }

  private def getExecutions(sqlStore: SQLAppStatusStore): Seq[CustomSQLMetrics] = {
    val executionList = sqlStore.executionsList(0, 100000)
    executionList.map(execution => convertToCaseClass(execution))
  }

  private def getAllMetrics(sqlStore: SQLAppStatusStore, executions: Seq[CustomSQLMetrics]): Map[Long, String] = {
    executions.flatMap(x => sqlStore.executionMetrics(x.executionId)).toMap
  }

  private def processNodes(sqlStore: SQLAppStatusStore, executions: Seq[CustomSQLMetrics], allMetrics: Map[Long, String]): Unit = {
    executions.flatMap(execution =>
      sqlStore.planGraph(execution.executionId).allNodes.map(node =>
        createPhysicalOpNode(execution, node, allMetrics)
      )
    ).foreach(node => client.add(node))
  }

  private def createPhysicalOpNode(execution: CustomSQLMetrics, node: SparkPlanGraphNode, allMetrics: Map[Long, String]): PhysicalOpNode = {
    PhysicalOpNode(
      context.applicationId,
      context.appName,
      node.id,
      execution.executionId,
      node.name,
      node.desc,
      node.metrics.map(metric =>
        SparkPlanMetric(metric.name, metric.metricType, allMetrics.getOrElse(metric.accumulatorId, "default"))
      ).filter(_.value != "default")
        .map(metric => metric.name -> metric.value).toMap
    )
  }

  private def processEdges(sqlStore: SQLAppStatusStore, executions: Seq[CustomSQLMetrics]): Unit = {
    executions.flatMap(execution =>
      sqlStore.planGraph(execution.executionId).edges.map(edge =>
        PhysicalOpEdge(context.appName, context.applicationId, execution.executionId, edge.fromId, edge.toId)
      )
    ).foreach(edge => client.add(edge))
  }

  private def saveExecutions(executions: Seq[CustomSQLMetrics]): Unit = {
    executions.foreach(execution => client.add(execution))
  }

  def convertToCaseClass(sqlExecutionUIData: SQLExecutionUIData): CustomSQLMetrics = {
    val metrics = sqlExecutionUIData.metrics.map {
      planMetric =>
        val name = planMetric.name
        val metricType = planMetric.metricType
        val accumulatorId = planMetric.accumulatorId
        val value = sqlExecutionUIData.metricValues.getOrElse(accumulatorId, "default")
        SparkPlanMetric(name, metricType, value)
    }
    val metricsMap = metrics.filter(x => x.value != "default").map { x => x.name -> x.value }.toMap
    CustomSQLMetrics(context.appName, context.applicationId, sqlExecutionUIData.executionId, sqlExecutionUIData.description, sqlExecutionUIData.details, sqlExecutionUIData.physicalPlanDescription, metricsMap, sqlExecutionUIData.completionTime, sqlExecutionUIData.stages.toList, sqlExecutionUIData.jobs.map(x => x._1).toList, sqlExecutionUIData.submissionTime)
  }

}
