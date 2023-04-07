package com.amazonaws.sparkobservability

import org.apache.logging.log4j.core.LogEvent
import org.slf4j.LoggerFactory
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider
import software.amazon.awssdk.auth.signer.Aws4Signer
import software.amazon.awssdk.auth.signer.params.Aws4SignerParams
import software.amazon.awssdk.core.sync.RequestBody
import software.amazon.awssdk.http.apache.ApacheHttpClient
import software.amazon.awssdk.http.{HttpExecuteRequest, SdkHttpFullRequest, SdkHttpMethod}
import software.amazon.awssdk.regions.Region

import java.io.ByteArrayInputStream
import java.net.URI
import java.util.HashMap
import scala.util.control.Exception
import com.google.gson.Gson

object ObservabilityClient {

  private val logger = LoggerFactory.getLogger(this.getClass.getName)
  private val gson = new Gson
  private val credentialsProvider = DefaultCredentialsProvider.create
  private val signer = Aws4Signer.create
  private val client = ApacheHttpClient.builder.build
  private val params: Aws4SignerParams = Aws4SignerParams.builder()
    .awsCredentials(credentialsProvider.resolveCredentials())
    .signingName("localhost")
    .signingRegion(Region.US_WEST_2)
    .build()

  def sendContent(content: String): Unit = {
    val request = SdkHttpFullRequest.builder
      .contentStreamProvider(RequestBody.fromString("[" + content + "]").contentStreamProvider())
      .method(SdkHttpMethod.POST)
      .putHeader("Content-Length", Integer.toString(content.length()+2))
      .putHeader("Content-Type", "application/json")
      .protocol("https")
      .uri(URI.create("http://localhost:2021/log/ingest"))
      .build

    val signedRequest = signer.sign(request, params)
    val executeRequest = HttpExecuteRequest.builder
      .request(signedRequest)
      .build

    logger.info("request sent to data prepper " + executeRequest.contentStreamProvider.get.toString)
    val response = client.prepareRequest(executeRequest).call
    logger.info("data prepper response :" + response.httpResponse.statusText())
    logger.info("data prepper response :" + response.httpResponse.statusCode)
    if (response.httpResponse.statusCode != 200) throw new Exception("error sending to data prepper")
  }

  def send(event: LogEvent): Unit = {
    val requestContent = new HashMap[String, Any](){
      put("message", event.getMessage.toString)
      put("logger", event.getLoggerFqcn)
      put("level", event.getLevel.toString)
    }
    logger.info("sending log " + requestContent.toString)
    logger.info("sending log as string " + event.toString)
    sendContent(event.toString)
  }

  def send(metrics: CustomMetrics): Unit = {
    val jsonString = gson.toJson(metrics)
    val requestContent = metrics.toMap
    logger.info("sending metrics " + requestContent.toString)
    logger.info("sending metrics as JSON string " + jsonString)
    sendContent(jsonString)
  }


}
