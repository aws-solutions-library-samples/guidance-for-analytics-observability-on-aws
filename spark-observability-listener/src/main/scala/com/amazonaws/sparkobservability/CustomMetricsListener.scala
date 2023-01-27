package com.amazonaws.sparkobservability

import org.apache.spark.scheduler.{SparkListenerStageCompleted, SparkListener, SparkListenerJobStart, SparkListenerTaskEnd}
import scala.collection.mutable.Map

class CustomMetricsListener extends SparkListener {

  override def onJobStart(jobStart: SparkListenerJobStart) {
    println(s"Job started with ${jobStart.stageInfos.size} stages: $jobStart")
  }

  override def onStageCompleted(stageCompleted: SparkListenerStageCompleted): Unit = {
    println(s"Stage ${stageCompleted.stageInfo.stageId} completed with ${stageCompleted.stageInfo.numTasks} tasks.")
  }

  override def onTaskEnd(taskEnded: SparkListenerTaskEnd){
    val metrics = collectMetrics(taskEnded)
    println(s"Metrics collected -> ${metrics}.")
  }

  def collectMetrics(taskEnded: SparkListenerTaskEnd): Map[Any, Any] = {
    val stageId = taskEnded.stageId
    val taskInfo = taskEnded.taskInfo
    val taskId = taskEnded.taskInfo.id
    val host = taskInfo.host
    val status = taskEnded.reason
    val executorId = taskInfo.executorId
    val partitionId = taskInfo.partitionId
    
    val metrics = taskEnded.taskMetrics

    var inputSizeRead = 0.0
    var inputRecordsRead = 0.0
    var runTime = 0.0

    if(metrics != null){
      runTime = metrics.executorRunTime
      val inputMetrics = metrics.inputMetrics
      if(inputMetrics != null){
        inputSizeRead =  inputMetrics.bytesRead
        inputRecordsRead =  inputMetrics.recordsRead
      }
    }

    return Map(
      "stageId"->stageId,
      "taskId"->taskId,
      "executorId"->executorId,
      "partitionId"->partitionId,
      "inputSizeRead"->inputSizeRead,
      "inputRecordsRead"->inputRecordsRead,
      "runTime"->runTime
    )
  }
}
