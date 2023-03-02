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

host = os.environ['DOMAIN']
region = os.environ['AWS_REGION']
credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(credentials, region)
user_secret_arn = os.environ['USER_SECRET_ARN']

session = requests.Session()
client = boto3.client('secretsmanager')

pipeline_role_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/pipeline_role.json"
pipeline_role_mapping_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/pipeline_role_mapping.j2"
pipeline_iam_role = os.environ['PIPELINE_ROLE_ARN']
user_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/user.j2"

awsauth = AWS4Auth(credentials.access_key,
                   credentials.secret_key,
                   region,
                   'es',
                   session_token=credentials.token)


def get_secret():
    """
    Retrieves the secret value from Secrets Manager.
    """
    try:
        response = client.get_secret_value(SecretId=user_secret_arn)
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
        raise Exception(f'Error {response.status_code} : {response.text}')

    # create the role mapping for pipeline
    logger.info(f'Reading role mapping template at {pipeline_role_mapping_path}')
    with open(pipeline_role_mapping_path) as file_:
        content = file_.read()
    template = Template(content)
    payload = template.render(backend_role=pipeline_iam_role)
    path = "_opendistro/_security/api/rolesmapping/pipeline_role"

    response = send_to_es('PUT', path, json.loads(payload))

    if not response.ok:
        raise Exception(f'Error {response.status_code} : {response.text}')

    # create the user for dashboard
    secret = get_secret()
    logger.info(f'Reading user definition at {user_path}')
    with open(user_path) as file_:
        content = file_.read()
    template = Template(content)
    payload = template.render(secret_password=secret['password'])
    path = f"_plugins/_security/api/internalusers/{secret['username']}"
    response = send_to_es('PUT', path, json.loads(payload))

    if not response.ok:
        raise Exception(f'Error {response.status_code} : {response.text}')


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
        raise Exception(f'Error {response.status_code} : {response.text}')

    # delete the role mapping for pipeline
    path = '_opendistro/_security/api/rolesmapping/pipeline_role'

    response = send_to_es('DELETE', path)

    if not response.ok:
        raise Exception(f'Error {response.status_code} : {response.text}')

    # delete the user for dashboard
    secret = get_secret()
    path = f"_plugins/_security/api/internalusers/{secret['username']}"

    response = send_to_es('DELETE', path)

    if not response.ok:
        raise Exception(f'Error {response.status_code} : {response.text}')
