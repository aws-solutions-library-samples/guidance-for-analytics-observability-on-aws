package com.amazonaws.sparkobservability

import org.apache.logging.log4j.core.LogEvent
import org.apache.logging.log4j.core.appender.AbstractAppender
import org.apache.logging.log4j.core.config.plugins.{Plugin, PluginAttribute, PluginFactory}

import scala.collection.mutable.ListBuffer

@Plugin(name = "SparkObs", category = "Core", elementType = "appender", printObject = true)
class CollectorAppender(name: String, endpoint: String, region: String, batchSize: Int) extends AbstractAppender(name, null, null, false, null) {

  private val client = new ObservabilityClient[LogEvent](endpoint, region, batchSize)

  override def append(event: LogEvent): Unit = {
    client.add(event)
  }
}

object CollectorAppender {

  @PluginFactory
  def createAppender(@PluginAttribute("name") name: String, @PluginAttribute("endpoint") endpoint: String, @PluginAttribute("region") region: String, @PluginAttribute("batchSize") batchSize: Int): CollectorAppender = {
    new CollectorAppender(name, endpoint, region, batchSize)
  }
}
