package com.amazonaws.sparkobservability

import java.time.Instant
import org.apache.logging.log4j.core.{Appender, Core, LogEvent}
import org.apache.logging.log4j.core.appender.AbstractAppender
import org.apache.logging.log4j.core.config.plugins.{Plugin, PluginFactory}
import org.apache.logging.log4j.{LogManager, Logger}

import scala.collection.mutable

@Plugin(name = "Custom", category = "Core", elementType = "appender", printObject = true)
class CustomLogsAppender extends AbstractAppender("CustomAppender", null, null, false, null) {
  val eventMap: mutable.Map[String, LogEvent] = mutable.Map[String, LogEvent]()

  override def append(event: LogEvent): Unit = {
    eventMap.put(Instant.now().toString(), event)
    println("custom log "+ObservabilityConf.sparkAppName)
    println(event.getMessage.getFormattedMessage)
  }
}

object CustomLogsAppender {
  @PluginFactory
  def createAppender(): CustomLogsAppender = {
    new CustomLogsAppender()
  }
}
