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

@Plugin(name = "SparkObs", category = "Core", elementType = "appender", printObject = true)
class CollectorAppender(name: String, endpoint: String, region: String, batchSize: Int, timeThreshold: Int) extends AbstractAppender(name, null, null, false, null) {

  private val client = new ObservabilityClient[LogEvent](endpoint, region, batchSize, timeThreshold)


  override def append(event: LogEvent): Unit = {

    client.add(Utils.enrichLogEvent(event))
  }
}

object CollectorAppender {

  @PluginFactory
  def createAppender(@PluginAttribute("name") name: String, @PluginAttribute("endpoint") endpoint: String, @PluginAttribute("region") region: String, @PluginAttribute("batchSize") batchSize: Int, @PluginAttribute("timeThreshold") timeThreshold: Int): CollectorAppender = {
    new CollectorAppender(name, endpoint, region, batchSize, timeThreshold)
  }
}
