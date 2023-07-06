# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0


import base64
import json
import logging
import os

import boto3
import requests
from botocore.exceptions import ClientError
from jinja2 import Template
from opensearchpy import AWSV4SignerAuth
from requests_aws4auth import AWS4Auth

logger = logging.getLogger()
logger.setLevel(logging.INFO)

host = os.environ['DOMAIN_ENDPOINT']
domain_name = os.environ['DOMAIN_NAME']
region = os.environ['AWS_REGION']
credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(credentials, region)
user_secret_arn = os.environ['USER_SECRET_ARN']
admin_secret_arn = os.environ['ADMIN_SECRET_ARN']

session = requests.Session()
ssm_client = boto3.client('secretsmanager')
os_client = boto3.client('opensearch')

pipeline_role_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/users/pipeline_role.json"
pipeline_role_mapping_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/users/pipeline_role_mapping.j2"
pipeline_iam_role = os.environ['PIPELINE_ROLE_ARN']
user_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/users/user.j2"
admin_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/users/admin.j2"
logs_template_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/templates/spark-logs.json"
stage_agg_template_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/templates/spark-stage-agg-metrics.json"
task_template_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/templates/spark-task-metrics.json"


awsauth = AWS4Auth(credentials.access_key,
                   credentials.secret_key,
                   region,
                   'es',
                   session_token=credentials.token)


def get_secret(secret_arn: str):
    """
    Retrieves the secret value from Secrets Manager.
    """
    try:
        response = ssm_client.get_secret_value(SecretId=secret_arn)
    except ClientError as e:
        logger.error(f"Failed to get secret: {e}")
        raise e
    else:
        if 'SecretString' in response:
            secret = response['SecretString']
        else:
            secret = base64.b64decode(response['SecretBinary'])
        return json.loads(secret)


def send_to_es(action: str, path: str, payload: json = None):
    """
    Sends a request to OpenSearch service with AWS4Auth.
    """
    url = f"https://{host}/{path}"

    if action == 'PUT':
        r = session.put(url, auth=awsauth, json=payload)
    elif action == 'DELETE':
        r = session.delete(url, auth=awsauth)
    else:
        raise Exception('HTTP action not supported')
    logger.info(r.text)
    return r


def on_event(event: json, context):
    logger.info(event)
    request_type = event['RequestType']
    if request_type == 'Create': return on_create(event)
    if request_type == 'Update': return on_update(event)
    if request_type == 'Delete': return on_delete(event)
    raise Exception("Invalid request type: %s" % request_type)


def on_create(event: json):
    props = event["ResourceProperties"]
    logger.info("create new resource with props %s" % props)

    # create role for pipeline
    logger.info(f'Reading role at {pipeline_role_path}')
    with open(pipeline_role_path) as file_:
        content = file_.read()
    payload = json.loads(content)
    path = '_opendistro/_security/api/roles/pipeline_role'

    response = send_to_es('PUT', path, payload)

    if not response.ok:
        raise Exception(f'Error {response.status_code} in pipeline role creation: {response.text}')

    # create the role mapping for pipeline
    logger.info(f'Reading role mapping template at {pipeline_role_mapping_path}')
    with open(pipeline_role_mapping_path) as file_:
        content = file_.read()
    template = Template(content)
    payload = template.render(backend_role=pipeline_iam_role)
    path = "_opendistro/_security/api/rolesmapping/pipeline_role"

    response = send_to_es('PUT', path, json.loads(payload))

    if not response.ok:
        raise Exception(f'Error {response.status_code} in pipeline role mapping creation: {response.text}')

    # enable internal database users
    logger.info(f'Updating domain config to enable internal database users')
    response = os_client.update_domain_config(
        DomainName=domain_name,
        AdvancedSecurityOptions={
            "InternalUserDatabaseEnabled": True
        }
    )
    logger.info(response)
    status_code = response['ResponseMetadata']['HTTPStatusCode']
    if status_code is not 200:
        raise Exception(f'Error {status_code} in domain security configuration update: {response["ResponseMetadata"]}')

    # create the admin for dashboard
    secret = get_secret(admin_secret_arn)
    logger.info(f'Reading admin definition at {admin_path}')
    with open(admin_path) as file_:
        content = file_.read()
    template = Template(content)
    payload = template.render(secret_password=secret['password'])
    path = f"_plugins/_security/api/internalusers/{secret['username']}"
    response = send_to_es('PUT', path, json.loads(payload))

    if not response.ok:
        raise Exception(f'Error {response.status_code} in admin user creation: {response.text}')

    # create the user for dashboard
    secret = get_secret(user_secret_arn)
    logger.info(f'Reading user definition at {user_path}')
    with open(user_path) as file_:
        content = file_.read()
    template = Template(content)
    payload = template.render(secret_password=secret['password'])
    path = f"_plugins/_security/api/internalusers/{secret['username']}"
    response = send_to_es('PUT', path, json.loads(payload))

    if not response.ok:
        raise Exception(f'Error {response.status_code} in read only user creation: {response.text}')

    # create the index template for spark logs
    logger.info(f'Reading logs index template at {logs_template_path}')
    with open(logs_template_path) as file_:
        content = file_.read()
    payload = json.loads(content)
    path = "_index_template/spark_logs"

    response = send_to_es('PUT', path, payload)

    if not response.ok:
        raise Exception(f'Error {response.status_code} in logs index template creation: {response.text}')

    # create the index template for spark task metrics
    logger.info(f'Reading task metrics index template at {task_template_path}')
    with open(task_template_path) as file_:
        content = file_.read()
    payload = json.loads(content)
    path = "_index_template/spark_task_metrics"

    response = send_to_es('PUT', path, payload)

    if not response.ok:
        raise Exception(f'Error {response.status_code} in task metrics index template creation: {response.text}')

    # create the index template for spark stage agg metrics
    logger.info(f'Reading stage agg metrics index template at {stage_agg_template_path}')
    with open(stage_agg_template_path) as file_:
        content = file_.read()
    payload = json.loads(content)
    path = "_index_template/spark_stage_agg_metrics"

    response = send_to_es('PUT', path, payload)

    if not response.ok:
        raise Exception(f'Error {response.status_code} in stage agg metrics index template creation: {response.text}')


def on_update(event: json):
    physical_id = event["PhysicalResourceId"]
    props = event["ResourceProperties"]
    logger.info("update resource %s with props %s" % (physical_id, props))
    # ...


def on_delete(event: json):
    physical_id = event["PhysicalResourceId"]
    logger.info("delete resource %s" % physical_id)

    # delete role for pipeline
    path = '_opendistro/_security/api/roles/pipeline_role'
    response = send_to_es('DELETE', path)
    if not response.ok:
        raise Exception(f'Error {response.status_code} in deleting the pipeline role: {response.text}')

    # delete the role mapping for pipeline
    path = '_opendistro/_security/api/rolesmapping/pipeline_role'
    response = send_to_es('DELETE', path)
    if not response.ok:
        raise Exception(f'Error {response.status_code} in deleting the pipeline role mapping: {response.text}')

    # delete the user for dashboard
    secret = get_secret(user_secret_arn)
    path = f"_plugins/_security/api/internalusers/{secret['username']}"
    response = send_to_es('DELETE', path)
    if not response.ok:
        raise Exception(f'Error {response.status_code} in deleting the dashboard user: {response.text}')

    # delete the admin for dashboard
    secret = get_secret(admin_secret_arn)
    path = f"_plugins/_security/api/internalusers/{secret['username']}"
    response = send_to_es('DELETE', path)
    if not response.ok:
        raise Exception(f'Error {response.status_code} in deleting the admin user: {response.text}')

    # delete index template for spark logs
    path = "_index_template/spark_logs"
    response = send_to_es('DELETE', path)
    if not response.ok:
        raise Exception(f'Error {response.status_code} in deleting the template for logs: {response.text}')

    # delete index template for spark task metrics
    path = "_index_template/spark_task_metrics"
    response = send_to_es('DELETE', path)
    if not response.ok:
        raise Exception(f'Error {response.status_code} in deleting the template for task metrics: {response.text}')

    # delete index template for spark stage agg metrics
    path = "_index_template/spark_stage_agg_metrics"
    response = send_to_es('DELETE', path)
    if not response.ok:
        raise Exception(f'Error {response.status_code} in deleting the template for stage agg metrics: {response.text}')