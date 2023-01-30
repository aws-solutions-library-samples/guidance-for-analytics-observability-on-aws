package com.amazonaws.sparkobservability

import org.apache.spark.api.plugin.{DriverPlugin, ExecutorPlugin, PluginContext, SparkPlugin}
import org.apache.spark.{SparkContext, SparkEnv}
import org.slf4j.LoggerFactory

import java.util
import java.util.Collections


class CollectorPlugin extends SparkPlugin{

  private val logger = LoggerFactory.getLogger(this.getClass.getName)

  override def driverPlugin(): DriverPlugin = new DriverPlugin {
    override def init(sc : SparkContext, ctx: PluginContext): util.Map[String,String]   = {
      logger.warn("Observability context on driver set for application "
        + SparkEnv.get.conf.get("spark.app.name")
        +" and run id "+ Utils.getAppId
      )
      Collections.emptyMap()
    }
  }

  override def executorPlugin(): ExecutorPlugin = new ExecutorPlugin {
    override def init(ctx: PluginContext, extraConf: util.Map[String, String]): Unit = {
      logger.warn("Observability context on executor set for application "
        + SparkEnv.get.conf.get("spark.app.name")
        +" and run ID "+ Utils.getAppId
        +" and for executor id "+ SparkEnv.get.executorId
      )
    }
  }
}
