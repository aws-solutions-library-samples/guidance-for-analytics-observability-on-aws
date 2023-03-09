package com.amazonaws.sparkobservability

import org.apache.http.HttpHost
import org.apache.http.conn.ssl.{NoopHostnameVerifier, TrustAllStrategy}
import org.apache.logging.log4j.core.LogEvent
import org.apache.logging.log4j.core.appender.AbstractAppender
import org.apache.logging.log4j.core.config.plugins.{Plugin, PluginAttribute, PluginFactory}
import org.apache.spark.SparkEnv
import org.opensearch.action.index.IndexRequest
import org.opensearch.client.{RequestOptions, RestClient, RestClientBuilder, RestHighLevelClient}
import org.apache.http.impl.nio.client.HttpAsyncClientBuilder
import org.apache.http.ssl.SSLContextBuilder
import org.opensearch.client.RestClientBuilder

import java.util
import scala.util.Try

@Plugin(name = "SparkObs", category = "Core", elementType = "appender", printObject = true)
class CollectorAppender(name: String) extends AbstractAppender(name, null, null, false, null) {

  override def append(event: LogEvent): Unit = {
    ObservabilityClient.send(event)
  }
}

object CollectorAppender {

  @PluginFactory
  def createAppender(@PluginAttribute("name") name: String): CollectorAppender = {
    new CollectorAppender(name)
  }
}
