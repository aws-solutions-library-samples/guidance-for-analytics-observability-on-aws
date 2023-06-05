package com.amazonaws.sparkobservability

import org.apache.logging.log4j.core.LogEvent
import org.apache.logging.log4j.core.appender.AbstractAppender
import org.apache.logging.log4j.core.config.plugins.{Plugin, PluginAttribute, PluginFactory}

@Plugin(name = "SparkObs", category = "Core", elementType = "appender", printObject = true)
class CollectorAppender(name: String, endpoint: String, region: String) extends AbstractAppender(name, null, null, false, null) {

  private val client = new ObservabilityClient(endpoint, region)

  override def append(event: LogEvent): Unit = {
    client.send(event)
  }
}

object CollectorAppender {

  @PluginFactory
  def createAppender(@PluginAttribute("name") name: String, @PluginAttribute("endpoint") endpoint: String, @PluginAttribute("region") region: String): CollectorAppender = {
    new CollectorAppender(name, endpoint, region)
  }
}
