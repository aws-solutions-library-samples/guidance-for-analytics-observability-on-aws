package com.amazonaws.sparkobservability

import org.apache.spark.SparkContext

import java.util
import org.apache.spark.api.plugin.{DriverPlugin, ExecutorPlugin, PluginContext, SparkPlugin}

object ObservabilityConf {
  var sparkAppName = ""
}

class CustomLogsPlugin extends SparkPlugin{

  override def driverPlugin(): DriverPlugin = null

  override def executorPlugin(): ExecutorPlugin = new ExecutorPlugin {
    override def init(ctx: PluginContext, extraConf: util.Map[String, String]): Unit = {
      ObservabilityConf.sparkAppName="test"
      println("plugin context: "+ctx.conf().get("spark.app.name"))
    }
  }
}
