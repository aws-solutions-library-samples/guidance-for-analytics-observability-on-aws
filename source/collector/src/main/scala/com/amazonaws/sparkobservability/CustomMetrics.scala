// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

package com.amazonaws.sparkobservability

import scala.collection.JavaConverters._
import org.joda.time.DateTime


/**
 * Abstract class that serves as the base class for all custom metrics.
 */

sealed abstract class CustomMetrics(val appName: String, val appId: String, val jobId: String, val metricsType: String, val metricTime: Long) extends Product {

  /**
   * Convert the metric object into a map representation.
   * @return A Java Map with key/value pairs.
   */
  def toMap() = {
    this.getClass.getDeclaredFields.map(_.getName).zip(this.productIterator.to).toMap.asJava
  }
}

/**
 * Case class that represents metrics extracted from Spark tasks
 */
case class CustomTaskMetrics(
                            override val appName: String,
                            override val appId: String,
                            override val jobId: String,
                            stageId: Integer,
                            stageAttemptId: Integer,
                            taskId: String,
                            executorId: String,
                            partitionId: Int,
                            inputBytesRead: Double,
                            inputRecordsRead: Double,
                            runTime: Double,
                            executorCpuTime: Double,
                            peakExecutionMemory: Double,
                            outputRecordsWritten: Double,
                            outputBytesWritten: Double,
                            shuffleRecordsRead: Double,
                            shuffleBytesRead: Double,
                            shuffleRecordsWritten: Double,
                            shuffleBytesWritten: Double,
                            override val metricTime: Long
                            ) extends CustomMetrics(appName, appId, jobId, metricsType="taskMetrics", metricTime)

/**
 * Case class that represents a subset of metrics extracted from Spark tasks and used to process metrics aggregation
 */
case class CustomLightTaskMetrics(
                            override val appName: String,
                            override val appId: String,
                            override val jobId: String,
                            stageId: Integer,
                            taskId: String,
                            inputBytesRead: Double,
                            shuffleBytesRead: Double,
                            override val metricTime: Long
                            ) extends CustomMetrics(appName, appId, jobId, metricsType="lightTaskMetrics", metricTime)

/**
 * Case class that represents metrics aggregated from tasks at the stage level
 */
case class CustomStageAggMetrics(
                             override val appName: String,
                             override val appId: String,
                             override val jobId: String,
                             stageId: Integer,
                             inputBytesReadSkewness: Double,
                             maxInputBytesRead: Double,
                             shuffleBytesReadSkewness: Double,
                             maxShuffleBytesRead: Double,
                            override val metricTime: Long
                            ) extends CustomMetrics(appName, appId, jobId, metricsType="stageAggMetrics", metricTime)