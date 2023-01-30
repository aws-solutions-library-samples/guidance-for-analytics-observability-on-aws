package com.amazonaws.sparkobservability

import org.apache.http.HttpHost
import org.opensearch.client.{RestClientBuilder, RestHighLevelClient}
import org.apache.http.impl.nio.client.HttpAsyncClientBuilder
import org.opensearch.client.RestClient

object OpensearchClient {

  private val builder: RestClientBuilder = RestClient.builder(new HttpHost("localhost", 9200, "https"))
    .setHttpClientConfigCallback(
      new RestClientBuilder.HttpClientConfigCallback() {
        override def customizeHttpClient(httpClientBuilder: HttpAsyncClientBuilder): HttpAsyncClientBuilder =
          HttpAsyncClientBuilder.create()
  })

  val client : RestHighLevelClient = new RestHighLevelClient(builder)

}
