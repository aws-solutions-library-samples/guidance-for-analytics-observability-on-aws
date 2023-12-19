// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

name := "spark-observability-collector"
organization := "com.amazonaws.sparkobservability"
version := "0.0.1"

scalaVersion := "2.12.17"

libraryDependencies ++= {
  Seq(
    "org.apache.spark" %% "spark-core" % "3.3.0" % "provided",
    "org.apache.logging.log4j" % "log4j-core" % "2.17.2",
    "software.amazon.awssdk" % "regions" % "2.20.38",
    "software.amazon.awssdk" % "apache-client" % "2.20.38",
    "software.amazon.awssdk" % "core" % "2.20.38",
    "software.amazon.awssdk" % "auth" % "2.20.38",
    "com.google.code.gson" % "gson" % "2.10.1",
    "com.lmax" % "disruptor" % "3.3.4",
    "org.scalatest" %% "scalatest" % "3.2.15" % "test",
    "org.scalatestplus" %% "mockito-4-6" % "3.2.15.0" % "test"
  )
}

assembly/assemblyMergeStrategy := {
  case "module-info.class" => MergeStrategy.discard
  case "META-INF/versions/9/module-info.class" => MergeStrategy.discard
  case x =>
    val oldStrategy = (assembly/assemblyMergeStrategy).value
    oldStrategy(x)
}