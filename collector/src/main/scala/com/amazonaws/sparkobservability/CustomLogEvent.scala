package com.amazonaws.sparkobservability

import org.joda.time.DateTime

case class CustomLogEvent(
    message: String,
    timestamp: DateTime
) extends Serializable
