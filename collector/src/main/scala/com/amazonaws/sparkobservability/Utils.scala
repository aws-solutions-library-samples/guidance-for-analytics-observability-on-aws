package com.amazonaws.sparkobservability

import org.apache.spark.SparkEnv

import scala.util.Try

object Utils {

  /**
   * Safer method to get the AppName than the `SparkEnv.get.conf.get("spark.app.name")` because it can be undefined
   * @return The AppName or "APP NAME NOT DEFINED"
   */
  def getAppName(): String = {
    Try(SparkEnv.get.conf.get("spark.app.name")).getOrElse("APP ID NOT DEFINED")
  }

  /**
   * Safer method to get the AppId than the `SparkEnv.get.conf.getAppId` because it can be undefined
   * @return The AppId or "APP ID NOT DEFINED"
   */
  def getAppId(): String = {
    Try(SparkEnv.get.conf.getAppId).getOrElse("APP ID NOT DEFINED")
  }

  def getObservabilityEndpoint(): String = {
    Try(SparkEnv.get.conf.get("spark.observability.endpoint")).getOrElse("OBSERVABILITY ENDPOINT NOT DEFINED")
  }

  def getAwsRegion(): String = {
    Try(SparkEnv.get.conf.get("spark.aws.region")).getOrElse("AWS REGION NOT DEFINED")
  }
}