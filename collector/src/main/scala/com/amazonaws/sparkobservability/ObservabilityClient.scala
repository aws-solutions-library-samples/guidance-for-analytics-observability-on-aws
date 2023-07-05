package com.amazonaws.sparkobservability

import com.google.gson.{Gson, JsonElement, JsonParser}
import org.apache.logging.log4j.ThreadContext
import org.apache.logging.log4j.core.LogEvent
import org.apache.logging.log4j.core.impl.Log4jLogEvent

import java.time.Instant
import org.apache.logging.log4j.message.SimpleMessage
import org.apache.logging.log4j.util.SortedArrayStringMap
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
import scala.collection.mutable.ListBuffer
import scala.util.Try



class ObservabilityClient[A](endpoint: String, region: String, batchSize: Int, timeThreshold: Int) {

  // private lazy val logger = LoggerFactory.getLogger(this.getClass.getName)
  private val credentialsProvider = DefaultCredentialsProvider.create
  private val signer = Aws4Signer.create
  private val client = ApacheHttpClient
    .builder.maxConnections(10)
    .build
  private lazy val params: Aws4SignerParams = Aws4SignerParams.builder()
    .awsCredentials(credentialsProvider.resolveCredentials())
    .signingName("osis")
    // TODO validate region and fail fast
    .signingRegion(Region.of(region))
    .build()
  // TODO validate it's an HTTPS URL with a path after the URI and fail fast
  private lazy val target = URI.create(endpoint)
  private val buffer = ListBuffer[A]()
  private val bufferIncomplete = ListBuffer[A]()
  private val gson = new Gson
  private var lastEventTimestamp: Instant = Instant.now
  private var firstRecord: Boolean = true


  def sendContent(content: String): Unit = {
    // logger.info("content sent: " + content)
    val request = SdkHttpFullRequest.builder
      .contentStreamProvider(RequestBody.fromString(content).contentStreamProvider)
      .method(SdkHttpMethod.POST)
      .putHeader("Content-Length", Integer.toString(content.length()))
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
    val preparedRequest = client.prepareRequest(executeRequest)

    val response = preparedRequest.call
    // logger.info("data prepper response :" + Try(response.httpResponse.statusText()).getOrElse("NO RESPONSE"))
    // logger.info("data prepper response :" + response.httpResponse.statusCode)
    if (response.httpResponse.statusCode != 200)
      throw new Exception("error sending to data prepper: "
        + response.httpResponse.statusCode + " "
        + Try(response.httpResponse.statusText()).getOrElse("NO RESPONSE")
      )
    preparedRequest.abort
  }

  private def timeSinceLastEvent(): Int = {
    val duration = java.time.Duration.between(lastEventTimestamp, Instant.now)
    duration.getSeconds.toInt
  }

  private def validateEvent(event: Any): Boolean = {
    if (event.isInstanceOf[LogEvent]) {
      val map = event.asInstanceOf[LogEvent].getContextData.toMap
      if (map.get("appName") == "UNDEFINED" || map.get("appId") == "UNDEFINED" || map.get("executorId") == "UNDEFINED") {
        return false
      }
    }
    true
  }

  def flushEvents(): Unit = {
    val content = buffer.map { event =>
      val jsonElement = JsonParser.parseString(gson.toJson(event))
      val jsonObject = jsonElement.getAsJsonObject

      if (event.isInstanceOf[LogEvent]) {

        if(jsonObject.has("contextData")) {
          val contextDataMap = event.asInstanceOf[LogEvent].getContextData.toMap
          jsonObject.remove("contextData")
          contextDataMap.entrySet().forEach((entry => jsonObject.addProperty(entry.getKey, entry.getValue)))
        }
      }
      jsonObject.toString
    }.reduceOption((x, y) => x + "," + y)

    content match {
      case Some(c) => {
        sendContent("[" + c + "]")
        buffer.clear()
      }
      case None => println("no record to send...")
    }
  }

  def add(event: A): Unit = {
    val prevTimeSinceLastEvent = timeSinceLastEvent()
    if (validateEvent(event)) {
      buffer += event
      if (bufferIncomplete.length > 0) {
        buffer ++= bufferIncomplete.map(e => Utils.enrichLogEvent(e.asInstanceOf[LogEvent], Some(event.asInstanceOf[LogEvent]))).asInstanceOf[ListBuffer[A]]
        bufferIncomplete.clear()
      }
    }
    else {
      bufferIncomplete += event
      return
    }
    lastEventTimestamp = Instant.now
    if  (firstRecord == false) {
      if ( buffer.size >= batchSize || prevTimeSinceLastEvent >= timeThreshold) {
        flushEvents()
      }
    } else firstRecord = false
  }
}
