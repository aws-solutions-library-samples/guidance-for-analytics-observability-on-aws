name := "spark-observability-collector"
organization := "com.amazonaws.sparkobservability"
version := "0.0.1"

scalaVersion := "2.12.17"

libraryDependencies ++= {
  Seq(
    "org.apache.spark" %% "spark-core" % "3.3.0" % "provided",
    "org.opensearch.client" % "opensearch-rest-high-level-client" % "2.5.0",
    "org.apache.logging.log4j" % "log4j-core" % "2.17.2"
  )
}

assembly/assemblyMergeStrategy := {
  case "module-info.class" => MergeStrategy.discard
  case "META-INF/versions/9/module-info.class" => MergeStrategy.discard
  case x =>
    val oldStrategy = (assembly/assemblyMergeStrategy).value
    oldStrategy(x)
}