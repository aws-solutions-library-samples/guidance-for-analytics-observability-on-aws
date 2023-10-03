// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

package com.amazonaws.sparkobservability

import com.google.gson.{Gson, JsonParser}
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider
import software.amazon.awssdk.auth.signer.Aws4Signer
import software.amazon.awssdk.auth.signer.params.Aws4SignerParams
import software.amazon.awssdk.core.exception.{NonRetryableException, RetryableException, SdkServiceException}
import software.amazon.awssdk.core.sync.RequestBody
import software.amazon.awssdk.http.apache.ApacheHttpClient
import software.amazon.awssdk.http.{HttpExecuteRequest, HttpExecuteResponse, SdkHttpFullRequest, SdkHttpMethod}
import software.amazon.awssdk.regions.Region

import java.net.URI
import java.time.{Duration, Instant}
import scala.collection.mutable.ListBuffer
import scala.util.{Failure, Success, Try}

/**
 * Contains static variables used by ObservabilityClient objects
 */
object ObservabilityClient{
  private val UNDEFINED_CONST : String = "UNDEFINED"
  // The maximum number of retries in an exponential back-off retry cycle
  private val MAX_RETRIES = 5
  // The initial time to wait before retrying
  private val INITIAL_BACKOFF = 5
  // The maximum time to wait before retrying
  private val MAX_BACKOFF = 60
}

/**
 * Client used to send records to the Observability solution.
 * The client is sending records to Amazon Opensearch Ingestion service via sigV4 HTTP requests.
 * @param endpoint the endpoint of the Opensearch Ingestion pipeline in the form of https://<NAME><HASH>.<REGION>.osis.amazonaws.com/<POSTFIX>
 * @param region the AWS region where the Opensearch Ingestion pipeline is deployed
 * @param batchSize the number of records to bufferize before they are sent to the ingestion pipeline
 * @param batchTime the maximum time between batches are sent to the ingestion pipeline
 * @tparam A the type of records that can be sent through the client
 */
class ObservabilityClient[A](endpoint: String, region: String, batchSize: Int, batchTime: Int) {

  /**
   * The credentials to authenticate HTTPS requests
   */
  private val credentialsProvider = DefaultCredentialsProvider.create

  /**
   * The signer to sign HTTPS requests with AWS credentials and authenticate to the ingestion pipeline
   */
  private val signer = Aws4Signer.create

  /**
   * The HTTPS client used to connect to Opensearch Ingestion pipeline
   */
  private val client = ApacheHttpClient
    // TODO dynamic number? parameter?
    .builder.maxConnections(4)
    .build

  /**
   * The parameters for signing the HTTPS requests
   */
  private lazy val params: Aws4SignerParams = Aws4SignerParams.builder()
    .awsCredentials(credentialsProvider.resolveCredentials())
    .signingName("osis")
    // TODO validate region and fail fast
    .signingRegion(Region.of(region))
    .build()

  /**
   * The HTTPS URI for the Opensearch Ingestion pipeline endpoint
   */
  // TODO validate it's an HTTPS URL with a path after the URI and fail fast
  private lazy val target = URI.create(endpoint)

  /**
   * The buffer used to batch records. When batch size is reached, the buffer is sent
   */
  private val buffer = ListBuffer[A]()

  /**
   * The time of the last flush to guarantee frequent delivery when batch size is not reached.
   * Add 10 seconds to the initial flush time to avoid sending first event outside of a batch (Spark takes 10s to init)
   */
  private var lastFlush: Instant = Instant.now.plus(Duration.ofSeconds(10))

  /**
   * Client is in an exponential back-off retry cycle or not
   */
  private var isBackingOff = false

  /**
   * The current time to wait before the next retry
   */
  private var backOff = ObservabilityClient.INITIAL_BACKOFF

  /**
   * The remaining number of retries before throwing an exception and stopping the collection
   */
  private var retries = ObservabilityClient.MAX_RETRIES

  /**
   * The JSON object manipulator
   */
  private val gson = new Gson

  /**
   * Spark context metadata used to enrich logs
   */
  private var appName : String = ObservabilityClient.UNDEFINED_CONST

  /**
   * Spark context metadata used to enrich logs
   */
  private var appId : String = ObservabilityClient.UNDEFINED_CONST

  /**
   * Spark context metadata used to enrich logs
   */
  private var executorId : String = ObservabilityClient.UNDEFINED_CONST

  /**
   * Set the last flush time to an Instant. Used to initialize the batching process after Spark application has started.
   * @param time The Instant to set the lastFlush
   */
  def setLastFlush(time: java.time.Instant): Unit = {
    lastFlush = time
  }

  /**
   * Return the status of the context composed of the application name, the application ID and the executor ID are known
   * @return True if all metadata is known, False otherwise
   */
  def logContextInitialized() : Boolean = {
    if ((appName != ObservabilityClient.UNDEFINED_CONST) &&
      (appId != ObservabilityClient.UNDEFINED_CONST) &&
      (executorId != ObservabilityClient.UNDEFINED_CONST)) {
      return true
    }
    false
  }

  /**
   * Send String content to Opensearch Ingestion pipeline via the HTTPS client.
   * The method throws two types of exceptions: non-retryable and retryable.
   * The type of exception is used to start an exponential back-off retry cycle or not.
   * @param content The string to send to Opensearch Ingestion pipeline (generally a JSON)
   */
  def sendContent(content: String): Unit = {
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

    val response: Try[HttpExecuteResponse] = Try(preparedRequest.call)

    response match {
      case Success(httpResponse) => {
        if (httpResponse.httpResponse.statusCode != 200)
          throw RetryableException.create("Error sending to Opensearch Ingestion pipeline: " +
            httpResponse.httpResponse.statusCode + " " +
            Try(httpResponse.httpResponse.statusText()).getOrElse("NO RESPONSE"))
        preparedRequest.abort
      }
      case Failure(e) => {
        e.getMessage.contains("InternalFailure") ||
        e.getMessage.contains("RequestAbortedException") ||
        e.getMessage.contains("RequestExpired") ||
        e.getMessage.contains("RequestTimeoutException") ||
        e.getMessage.contains("ServiceUnavailable") ||
        e.getMessage.contains("ThrottlingException")
        match {
          case true => throw RetryableException.create(e.getMessage)
          case false => throw NonRetryableException.create(e.getMessage)
        }
      }
    }
  }

  /**
   * Gives the duration in seconds since the last successful flush.
   * Takes into account the exponential back-off retry by subtracting the current backoff duration.
   * @return the number of seconds since the last successful flush
   */
  private def durationSinceLastFlush(): Int = {
    val duration = java.time.Duration.between(lastFlush, Instant.now)
    // If the client is in a retry cycle, subtract the current backoff duration
    isBackingOff match{
      case true => duration.getSeconds.toInt - backOff
      case false => duration.getSeconds.toInt
    }
  }

  /**
   * Initialize the log context by collecting the application name, the application ID and the executor ID.
   */
  private def initLogContext(): Unit = {
    this.appName = Utils.getAppName()
    this.appId = Utils.getAppId()
    this.executorId = Utils.getExecutorId()
  }

  /**
   * Flush events from the buffer to the Opensearch Ingestion pipeline.
   * This method converts each event in the buffer to a JSON string and sends it.
   * If the log context is not initialized, it initializes it and recursively calls the flushEvents method.
   * After sending the events, it clears the buffer and updates the backoff and retry variables if necessary.
   * If an error occurs during sending, it checks if it is a retryable error and updates the backoff and retry variables accordingly.
   * If the error is non-retryable, it throws a NonRetryableException.
   */
  def flushEvents(): Unit = {
    val content = buffer.map { event =>
      val jsonElement = JsonParser.parseString(gson.toJson(event))
      val jsonObject = jsonElement.getAsJsonObject

        if (logContextInitialized()) {
          jsonObject.addProperty("appName", appName)
          jsonObject.addProperty("appId", appId)
          jsonObject.addProperty("executorId", executorId)
        }
        else {
          initLogContext()
          if (logContextInitialized()) {
            flushEvents()
          }
          return
        }
      jsonObject.toString
    }.reduceOption((x, y) => x + "," + y)

    content match {
      case Some(c) => {
        val flush = Try(sendContent ("[" + c + "]"))
        flush match{
          case Success(_) => {
            lastFlush = Instant.now
            buffer.clear()
            if (isBackingOff == true) {
              isBackingOff = false
              backOff = ObservabilityClient.INITIAL_BACKOFF
              retries = ObservabilityClient.MAX_RETRIES
            }
          }
          case Failure(e) =>
            if (e.isInstanceOf[RetryableException] && retries > 0) {
              isBackingOff = true
              backOff = (backOff * 2).min(ObservabilityClient.MAX_BACKOFF)
              retries -= 1
            } else {
              throw NonRetryableException.create("Non-retryable error sending records to Opensearch Ingestion pipeline: " + e.getMessage)
            }
        }
      }
      case None => println("no record to send...")
    }
  }

  /**
   * Add an event to the client buffer and flush events if conditions are met.
   * @param event the event to add to the client buffer
   */
  def add(event: A): Unit = {
    buffer += event
    if (isBackingOff) {
      if (durationSinceLastFlush() >= batchTime) flushEvents
    } else {
      if (buffer.size >= batchSize || durationSinceLastFlush() >= batchTime) flushEvents
    }
  }
}
