package com.amazonaws.sparkobservability

import org.apache.spark.api.plugin.{DriverPlugin, ExecutorPlugin, PluginContext, SparkPlugin}
import org.apache.spark.internal.Logging
import org.apache.spark.sql.execution.ui.SQLAppStatusListener
import org.apache.spark.SparkContext
import org.apache.spark.status._

import java.util
import scala.collection.JavaConverters.mapAsJavaMapConverter

/**
 * Helps initializing the CustomMetricsListener with spark context.
 */
class ObservabilityPlugin extends SparkPlugin {

  override def driverPlugin(): DriverPlugin = new ObservabilityDriverPlugin()
  override def executorPlugin(): ExecutorPlugin = null


  class ObservabilityDriverPlugin extends DriverPlugin with Logging {
    var sc: SparkContext = null
    var sqlFunction:  () => Option[SQLAppStatusListener] = null

    override def init(sc: SparkContext, pluginContext: PluginContext): util.Map[String, String] = {
      // this.sqlFunction = ObservabilitySql.install(sc)
      this.sqlFunction = Utils.getSqlListener(sc)
      this.sc = sc
      this.sc.addSparkListener(new CustomMetricsListener(sc, sqlFunction))
      Map[String, String]().asJava    }
  }
}

