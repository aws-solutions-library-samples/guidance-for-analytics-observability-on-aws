# Dockerfile
FROM public.ecr.aws/emr-serverless/spark/emr-6.9.0:latest

USER root

COPY log4j2.properties /etc/spark/conf/log4j2.properties

USER hadoop:hadoop