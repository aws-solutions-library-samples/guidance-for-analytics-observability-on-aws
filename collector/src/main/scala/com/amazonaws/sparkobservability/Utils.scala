package com.amazonaws.sparkobservability

import org.apache.logging.log4j.core.LogEvent
import org.apache.logging.log4j.core.impl.Log4jLogEvent
import org.apache.logging.log4j.util.SortedArrayStringMap
import org.apache.spark.SparkEnv

import scala.util.Try

/**
 * Utility object containing helper methods for retrieving Spark application information.
 */
object Utils {

  /**
   * Enriches a LogEvent with additional context data.
   * @param original The original LogEvent to enrich.
   * @param optionalEvent An optional LogEvent containing additional context data.
   * @return The enriched LogEvent.
   */
  def enrichLogEvent(original: LogEvent, optionalEvent: Option[LogEvent] = None): LogEvent = {

     val contextData = new SortedArrayStringMap()

    original.getContextData.forEach { (key: String, value: AnyRef) =>
      contextData.putValue(key, value)
    }

    optionalEvent match {
      case Some(event) =>
        contextData.putValue("appName", event.getContextData.getValue("appName"))
        contextData.putValue("appId", event.getContextData.getValue("appId"))
        contextData.putValue("executorId", event.getContextData.getValue("executorId"))
      case None =>
        contextData.putValue("appName", Utils.getAppName())
        contextData.putValue("appId", Utils.getAppId())
        contextData.putValue("executorId", Utils.getExecutorId())
    }

    Log4jLogEvent.newBuilder()
      .setLoggerName(original.getLoggerName)
      .setLoggerFqcn(original.getLoggerFqcn)
      .setLevel(original.getLevel)
      .setMessage(original.getMessage)
      .setThreadName(original.getThreadName)
      .setTimeMillis(original.getTimeMillis)
      .setThrown(original.getThrown)
      .setContextData(contextData)
      .setContextStack(original.getContextStack)
      .setSource(original.getSource)
      .setEndOfBatch(original.isEndOfBatch)
      .build()
  }

  /**
   * Safer method to get the AppName than the `SparkEnv.get.conf.get("spark.app.name")` because it can be undefined
   * @return The AppName or "APP NAME NOT DEFINED"
   */
  def getAppName(): String = {
      Try(SparkEnv.get.conf.get("spark.app.name")).getOrElse("UNDEFINED")
    }


  /**
   * Safer method to get the AppId than the `SparkEnv.get.conf.getAppId` because it can be undefined
   * @return The AppId or "APP ID NOT DEFINED"
   */
  def getAppId(): String = {
    Try(SparkEnv.get.conf.getAppId).getOrElse("UNDEFINED")
  }

  /**
   * Safer method to retrieve the executor ID than the `SparkEnv.get.executorId`because it can be undefined.
   * @return The executor ID or "UNDEFINED".
   */
  def getExecutorId() : String = {
    Try(SparkEnv.get.executorId).getOrElse("UNDEFINED")
  }

  /**
   * Retrieves the observability endpoint from Spark configuration.
   * @return The observability endpoint or "OBSERVABILITY ENDPOINT NOT DEFINED".
   */
  def getObservabilityEndpoint(): String = {
    Try(SparkEnv.get.conf.get("spark.metrics.endpoint")).getOrElse("OBSERVABILITY ENDPOINT NOT DEFINED")
  }

  /**
   * Retrieves the AWS region from Spark configuration.
   * @return The AWS region or "AWS REGION NOT DEFINED".
   */
  def getAwsRegion(): String = {
    Try(SparkEnv.get.conf.get("spark.metrics.region")).getOrElse("AWS REGION NOT DEFINED")
  }

  /**
   * Retrieves the batch size from Spark configuration.
   * @return The batch size or default value of 100.
   */
  def getBatchSize(): Int = {
    Try(SparkEnv.get.conf.get("spark.metrics.batchSize")).getOrElse("100").toInt
  }

  /**
   * Retrieves the time threshold from Spark configuration.
   * @return The time threshold or default value of 10.
   */
  def getTimeThreshold(): Int = {
    Try(SparkEnv.get.conf.get("spark.metrics.timeThreshold")).getOrElse("10").toInt
  }s
}
