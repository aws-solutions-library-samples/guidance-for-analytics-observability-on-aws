export APP_ID=00fammj5ncg3r709                                  #Your EMR Serverless Application Id from Previous Step
export query=$2                                                 #option query param, can skip if all tpc-ds queries are run
export RUNTIME_ROLE=arn:aws:iam::668876353122:role/EmrServerlessStack-EmrRoleBCD0A6A9-GPMAGDSNHBD2 #Runtime role setup from pre-req
export DESTINATION_BUCKET=emrserverlessstack-destinationbucket4becdb47-nku2ni2thgcs  #S3 bucket to write logs and benchmark results
export AWS_REGION=us-east-1                                     #region where app was created
export ITERATION=1

aws emr-serverless start-job-run --application-id $APP_ID \
--execution-role-arn "$RUNTIME_ROLE" \
--job-driver '{
   "sparkSubmit":{
      "entryPoint":"s3://aws-bigdata-blog/artifacts/oss-spark-benchmarking/spark-benchmark-assembly-3.3.0.jar",
      "entryPointArguments":[
         "s3://blogpost-sparkoneks-us-east-1/blog/BLOG_TPCDS-TEST-3T-partitioned",
         "s3://'$DESTINATION_BUCKET'/spark/EMRSERVERLESS_TPCDS-TEST-3T-RESULT",
         "/opt/tpcds-kit/tools",
         "parquet",
         "3000",
         "'$ITERATION'",
         "false",
         "q1-v2.4\\,q10-v2.4\\,q11-v2.4\\,q12-v2.4\\,q13-v2.4\\,q14a-v2.4\\,q14b-v2.4\\,q15-v2.4\\,q16-v2.4\\,q17-v2.4\\,q18-v2.4\\,q19-v2.4\\,q2-v2.4\\,q20-v2.4\\,q21-v2.4\\,q22-v2.4\\,q23a-v2.4\\,q23b-v2.4\\,q24a-v2.4\\,q24b-v2.4\\,q25-v2.4\\,q26-v2.4\\,q27-v2.4\\,q28-v2.4\\,q29-v2.4\\,q3-v2.4\\,q30-v2.4\\,q31-v2.4\\,q32-v2.4\\,q33-v2.4\\,q34-v2.4\\,q35-v2.4\\,q36-v2.4\\,q37-v2.4\\,q38-v2.4\\,q39a-v2.4\\,q39b-v2.4\\,q4-v2.4\\,q40-v2.4\\,q41-v2.4\\,q42-v2.4\\,q43-v2.4\\,q44-v2.4\\,q45-v2.4\\,q46-v2.4\\,q47-v2.4\\,q48-v2.4\\,q49-v2.4\\,q5-v2.4\\,q50-v2.4\\,q51-v2.4\\,q52-v2.4\\,q53-v2.4\\,q54-v2.4\\,q55-v2.4\\,q56-v2.4\\,q57-v2.4\\,q58-v2.4\\,q59-v2.4\\,q6-v2.4\\,q60-v2.4\\,q61-v2.4\\,q62-v2.4\\,q63-v2.4\\,q64-v2.4\\,q65-v2.4\\,q66-v2.4\\,q67-v2.4\\,q68-v2.4\\,q69-v2.4\\,q7-v2.4\\,q70-v2.4\\,q71-v2.4\\,q72-v2.4\\,q73-v2.4\\,q74-v2.4\\,q75-v2.4\\,q76-v2.4\\,q77-v2.4\\,q78-v2.4\\,q79-v2.4\\,q8-v2.4\\,q80-v2.4\\,q81-v2.4\\,q82-v2.4\\,q83-v2.4\\,q84-v2.4\\,q85-v2.4\\,q86-v2.4\\,q87-v2.4\\,q88-v2.4\\,q89-v2.4\\,q9-v2.4\\,q90-v2.4\\,q91-v2.4\\,q92-v2.4\\,q93-v2.4\\,q94-v2.4\\,q95-v2.4\\,q96-v2.4\\,q97-v2.4\\,q98-v2.4\\,q99-v2.4\\,ss_max-v2.4",
         "true"
      ],
      "sparkSubmitParameters":"--conf spark.driver.extraJavaOptions=-Dlog4j2.contextSelector=org.apache.logging.log4j.core.async.AsyncLoggerContextSelector --conf spark.jars=s3://spark-observability-099713751195/spark-observability-collector-assembly-0.0.1.jar --conf spark.extraListeners=com.amazonaws.sparkobservability.CustomMetricsListener --conf spark.obs.region=us-west-2 --conf spark.obs.endpoint=https://spark-obs-metrics-6shkttignlqeh4waglhefoy6ay.us-west-2.osis.amazonaws.com/ingest --class com.amazonaws.eks.tpcds.BenchmarkSQL"
   }
}' \
--configuration-overrides '{"monitoringConfiguration": {"s3MonitoringConfiguration": {"logUri": "s3://'$DESTINATION_BUCKET'/spark/logs/"}}}' \
--region "$AWS_REGION"