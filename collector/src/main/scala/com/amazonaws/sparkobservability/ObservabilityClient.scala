package com.amazonaws.sparkobservability

import com.google.gson.Gson
import org.apache.logging.log4j.core.LogEvent
import org.apache.spark.SparkEnv
import org.slf4j.LoggerFactory
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider
import software.amazon.awssdk.auth.signer.Aws4Signer
import software.amazon.awssdk.auth.signer.params.Aws4SignerParams
import software.amazon.awssdk.core.sync.RequestBody
import software.amazon.awssdk.http.apache.ApacheHttpClient
import software.amazon.awssdk.http.{HttpExecuteRequest, SdkHttpFullRequest, SdkHttpMethod}
import software.amazon.awssdk.regions.Region

import java.net.URI
import java.util.HashMap
import scala.util.Try

object ObservabilityClient {

  private val logger = LoggerFactory.getLogger(this.getClass.getName)
  private val gson = new Gson
  private val credentialsProvider = DefaultCredentialsProvider.create
  private val signer = Aws4Signer.create
  private val client = ApacheHttpClient.builder.build
  private val params: Aws4SignerParams = Aws4SignerParams.builder()
    .awsCredentials(credentialsProvider.resolveCredentials())
    .signingName("osis")
    .signingRegion(Region.of(Utils.getAwsRegion()))
    .build()
  private val target = URI.create(Utils.getObservabilityEndpoint())

  def sendContent(content: String): Unit = {
    logger.info("content sent: " + content)

    val request = SdkHttpFullRequest.builder
      .contentStreamProvider(RequestBody.fromString("[" + content + "]").contentStreamProvider)
      .method(SdkHttpMethod.POST)
      .putHeader("Content-Length", Integer.toString(content.length()+2))
      .putHeader("Content-Type", "application/json")
      .protocol("https")
      .uri(target)
      .encodedPath(target.getPath)
      .build

    val signedRequest = signer.sign(request, params)
    val executeRequest = HttpExecuteRequest.builder
      .request(signedRequest)
      .contentStreamProvider(Try(signedRequest.contentStreamProvider.get).getOrElse(null))
      .build

    val response = client.prepareRequest(executeRequest).call
    logger.info("data prepper response :" + Try(response.httpResponse.statusText()).getOrElse("NO RESPONSE"))
    logger.info("data prepper response :" + response.httpResponse.statusCode)
    if (response.httpResponse.statusCode != 200) throw new Exception("error sending to data prepper")
  }

  def send(event: LogEvent): Unit = {
    logger.info("sending log as string " + event.toString)
    sendContent(event.toString)
  }

  def send(metrics: CustomMetrics): Unit = {
    val jsonString = gson.toJson(metrics)
    val requestContent = metrics.toMap
    logger.info("sending metrics as JSON string " + jsonString)
    sendContent(jsonString)
  }


}
