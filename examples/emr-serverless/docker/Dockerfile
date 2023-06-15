# Dockerfile
FROM public.ecr.aws/emr-serverless/spark/emr-6.9.0:latest

USER root

COPY log4j2.properties /etc/spark/conf/log4j2.properties
COPY spark-observability-collector-assembly-0.0.1.jar /usr/lib/spark-observability-collector.jar

RUN sed -i -e 's/^\(spark.driver.extraClassPath\).*$/&:\/usr\/lib\/spark-observability-collector.jar/g' /etc/spark/conf/spark-defaults.conf && \
    sed -i -e 's/^\(spark.executor.extraClassPath\).*$/&:\/usr\/lib\/spark-observability-collector.jar/g' /etc/spark/conf/spark-defaults.conf

USER hadoop:hadoop