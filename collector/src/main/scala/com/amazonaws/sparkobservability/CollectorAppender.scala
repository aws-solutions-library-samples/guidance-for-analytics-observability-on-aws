package com.amazonaws.sparkobservability

import org.apache.logging.log4j.core.LogEvent
import org.apache.logging.log4j.core.appender.AbstractAppender
import org.apache.logging.log4j.core.config.plugins.{Plugin, PluginAttribute, PluginFactory}
import org.apache.logging.log4j.ThreadContext
import org.apache.logging.log4j.core.impl.Log4jLogEvent
import org.apache.logging.log4j.message.SimpleMessage
import org.apache.logging.log4j.util.SortedArrayStringMap
import org.apache.spark.{SparkConf, SparkEnv}

import scala.collection.mutable.{HashMap, ListBuffer}

/**
 * Log4j plugin implementing a custom appender to send log events to an ObservabilityClient.
 * @param name The name of the Log4j2 Appender
 * @param endpoint The endpoint of the Opensearch Ingestion pipeline
 * @param region The AWS region where the Opensearch Ingestion pipeline is deployed
 * @param batchSize the number of records to bufferize before they are sent to the ingestion pipeline
 * @param timeThreshold the maximum time between batches are sent to the ingestion pipeline
 */

@Plugin(name = "SparkObs", category = "Core", elementType = "appender", printObject = true)
class CollectorAppender(name: String, endpoint: String, region: String, batchSize: Int, timeThreshold: Int) extends AbstractAppender(name, null, null, false, null) {

  private val client = new ObservabilityClient[LogEvent](endpoint, region, batchSize, timeThreshold)

  /**
   * Override the append method of the AbstractAppender class.
   * Add the log event to the ObservabilityClient.
   * @param event The log event to be appended.
   */
  override def append(event: LogEvent): Unit = {
    client.add(event)
  }
}

object CollectorAppender {

  /**
   * Factory method to create instances of the CollectorAppender.
   * @param name The name of the Log4j2 Appender
   * @param endpoint The endpoint of the Opensearch Ingestion pipeline
   * @param region The AWS region where the Opensearch Ingestion pipeline is deployed
   * @param batchSize the number of records to bufferize before they are sent to the ingestion pipeline
   * @param timeThreshold the maximum time between batches are sent to the ingestion pipeline
   * @return An instance of the CollectorAppender class.
   */
  @PluginFactory
  def createAppender(@PluginAttribute("name") name: String, @PluginAttribute("endpoint") endpoint: String, @PluginAttribute("region") region: String, @PluginAttribute("batchSize") batchSize: Int, @PluginAttribute("timeThreshold") timeThreshold: Int): CollectorAppender = {
    new CollectorAppender(name, endpoint, region, batchSize, timeThreshold)
  }
}
