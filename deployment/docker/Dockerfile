# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
FROM public.ecr.aws/emr-serverless/spark/emr-6.9.0:20230906

USER root

COPY log4j2.xml /etc/spark/conf/log4j2.xml
COPY spark-observability-collector-assembly-0.0.1.jar /usr/lib/spark-observability-collector.jar

RUN sed -i -e 's/^\(spark.driver.extraClassPath\).*$/&:\/usr\/lib\/spark-observability-collector.jar/g' /etc/spark/conf/spark-defaults.conf && \
    sed -i -e 's/^\(spark.executor.extraClassPath\).*$/&:\/usr\/lib\/spark-observability-collector.jar/g' /etc/spark/conf/spark-defaults.conf && \
    rm -f /etc/spark/conf/log4j2.properties

USER hadoop:hadoop