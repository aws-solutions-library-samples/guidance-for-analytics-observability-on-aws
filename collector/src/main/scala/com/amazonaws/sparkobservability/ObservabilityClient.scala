package com.amazonaws.sparkobservability

import org.apache.http.HttpHost
import org.apache.http.conn.ssl.{NoopHostnameVerifier, TrustAllStrategy}
import org.apache.http.impl.nio.client.HttpAsyncClientBuilder
import org.apache.http.ssl.SSLContextBuilder
import org.apache.logging.log4j.core.LogEvent
import org.opensearch.action.index.IndexRequest
import org.opensearch.client.{RequestOptions, RestClient, RestClientBuilder, RestHighLevelClient}

import java.util

object ObservabilityClient {

  lazy val opensearchClient: RestHighLevelClient = {
    val builder = RestClient.builder(new HttpHost("localhost", 9200, "http"))
      .setHttpClientConfigCallback(
        new RestClientBuilder.HttpClientConfigCallback() {
          @Override
          override def customizeHttpClient(httpClientBuilder: HttpAsyncClientBuilder): HttpAsyncClientBuilder = {
            httpClientBuilder
              .setSSLContext(new SSLContextBuilder().loadTrustMaterial(null, TrustAllStrategy.INSTANCE).build())
              .setSSLHostnameVerifier(NoopHostnameVerifier.INSTANCE)
          }
        }
      )
    new RestHighLevelClient(builder)
  }

  def send(event: LogEvent): Unit = {
    val request = new IndexRequest("obs")
    val requestContent = new util.HashMap[String, String](){
      put("message: ", event.toString)
    }
    request.source(requestContent)
    opensearchClient.index(request, RequestOptions.DEFAULT)
  }
}
