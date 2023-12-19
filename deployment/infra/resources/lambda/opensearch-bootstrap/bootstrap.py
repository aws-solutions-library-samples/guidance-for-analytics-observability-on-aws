# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0


import base64
from email import header
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

pipeline_iam_role = os.environ['PIPELINE_ROLE_ARN']

pipeline_role_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/users/pipeline_role.json"
pipeline_role_mapping_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/users/pipeline_role_mapping.j2"
user_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/users/user.j2"
admin_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/users/admin.j2"
logs_template_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/templates/spark-logs.json"
stage_agg_template_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/templates/spark-stage-agg-metrics.json"
task_template_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/templates/spark-task-metrics.json"
data_skew_path = f"{os.environ['LAMBDA_TASK_ROOT']}/resources/dashboards/data-skew.ndjson"


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

def load_content(path: str):
    """
    Creates a payload for OpenSearch service.
    """
    logger.info(f'Reading from {path}')
    with open(path) as file_:
        content = file_.read()
    return content

def send_to_os(action: str, path: str, payload: str = None, headers: dict = None):
    """
    Sends a request to OpenSearch service with AWS4Auth.
    """
    url = f"https://{host}/{path}"

    if action == 'PUT':
        r = session.put(url, auth=awsauth, json=payload, headers=headers)
    elif action == 'DELETE':
        r = session.delete(url, auth=awsauth, headers=headers)
    elif action == 'POST':
        r = session.post(url, auth=awsauth, json=payload, headers=headers)
    elif action == 'POST_FILE':
        r = session.post(url, auth=awsauth, files={'file': payload}, headers=headers)
    else:
        raise Exception('HTTP action not supported')
    logger.info(r.text)
    return r

def os_resource(action: str, os_path: str, resource_path: str = None, headers: dict = None):
    """
    generic CRUD operation on Opensearch resources
    """
    if action == 'POST' or action == 'PUT':
        content = load_content(resource_path)
        payload = json.loads(content)
        return send_to_os(action=action, path=os_path, payload=payload, headers=headers)
    
    elif action == 'POST_FILE':
        payload = open(resource_path, 'rb')
        return send_to_os('POST_FILE', os_path, payload, headers)

    elif action == 'DELETE':
        return send_to_os(action=action, path=os_path, headers=headers)
    else:
        raise Exception('Resource action not supported, only POST, PUT or DELETE')

def saved_objects(name: str, action: str, resource_path: str = None, id : str = None, type: str = None):
    """
    Dashboards CRUD operations
    """
    if action == 'CREATE':
        logger.info(f'Creating {name} saved_objects at {resource_path}')
        response = os_resource(action='POST_FILE', os_path="_dashboards/api/saved_objects/_import?overwrite=true", resource_path=resource_path, headers={'osd-xsrf': 'true'})
        if not response.ok:
            raise Exception(f'Error {response.status_code} in {name} dashboard creation: {response.text}')
        
        results = response.json().get('successResults')
        for r in results:
            del r['meta']
            del r['overwrite']
        return results

    elif action == 'DELETE':
        response = os_resource(action='DELETE', os_path=f"_dashboards/api/saved_objects/{type}/{id}", headers={'osd-xsrf': 'true'})
        if not response.ok:
            raise Exception(f'Error {response.status_code} in deleting {name} dashboard: {response.text}')
        
    else:
        raise Exception('Resource action not supported, only CREATE or DELETE')
    
def index_template(name: str, action: str, resource_path: str = None, id : str = None):
    """
    Index template CRUD operations
    """
    if action == 'CREATE':
        logger.info(f'Creating {name} index template at {resource_path}')
        response = os_resource(action='PUT', os_path=f"_index_template/{name}", resource_path=resource_path)
        if not response.ok:
            raise Exception(f'Error {response.status_code} in {name} index template creation: {response.text}')
        
    elif action == 'DELETE':
        response = os_resource(action='DELETE', os_path=f"_index_template/{name}")
        if not response.ok:
            raise Exception(f'Error {response.status_code} in deleting {name} index template: {response.text}')

    else:
        raise Exception('Resource action not supported, only CREATE or DELETE')
    
def user(action: str, secret_arn: str, resource_path: str = None):
    """
    User CRUD operations
    """
    if action == 'CREATE':
        secret = get_secret(secret_arn)
        content = load_content(resource_path)
        payload = Template(content).render(secret_password=secret['password'])
        path = f"_plugins/_security/api/internalusers/{secret['username']}"
        response = send_to_os('PUT', path, json.loads(payload))

        if not response.ok:
            raise Exception(f'Error {response.status_code} in {secret_arn} creation: {response.text}')
    elif action == 'DELETE':
        secret = get_secret(secret_arn)
        path = f"_plugins/_security/api/internalusers/{secret['username']}"
        response = send_to_os('DELETE', path)

        if not response.ok:
            raise Exception(f'Error {response.status_code} in deleting {secret_arn}: {response.text}')

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
    os_resource('PUT', os_path=f"_opendistro/_security/api/roles/pipeline_role", resource_path=pipeline_role_path)

    # create the role mapping for pipeline
    content = load_content(pipeline_role_mapping_path)
    payload = Template(content).render(backend_role=pipeline_iam_role)
    path = "_opendistro/_security/api/rolesmapping/pipeline_role"

    response = send_to_os('PUT', path, json.loads(payload))

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
    if status_code != 200:
        raise Exception(f'Error {status_code} in domain security configuration update: {response["ResponseMetadata"]}')

    # create the admin for dashboard
    user('CREATE', secret_arn=admin_secret_arn, resource_path=admin_path)

    # create the user for dashboard
    user('CREATE', secret_arn=user_secret_arn, resource_path=user_path)

    # create the index template for spark logs
    index_template('spark_logs', 'CREATE', resource_path=logs_template_path)

    # create the index template for spark task metrics
    index_template('spark_task_metrics', 'CREATE', resource_path=task_template_path)

    # create the index template for spark stage agg metrics
    index_template('spark_stage_agg_metrics', 'CREATE', resource_path=stage_agg_template_path)

    # create the opensearch dashboards saved objects
    logger.info(f'Creating saved objects at {data_skew_path}')
    response = os_resource(action='POST_FILE', os_path="_dashboards/api/saved_objects/_import?overwrite=true", resource_path=data_skew_path, headers={'osd-xsrf': 'true'})
    if not response.ok:
        raise Exception(f'Error {response.status_code} in saved objects creation: {response.text}')
    resources = response.json()['successResults']
    for r in resources:
        if 'meta' in r:
            del r['meta']
        if 'overwrite' in r:
            del r['overwrite']
    return {    
        'Data': {
            'Resources': resources
        }
    }


def on_update(event: json):
    physical_id = event["PhysicalResourceId"]
    props = event["ResourceProperties"]
    logger.info("update resource %s with props %s" % (physical_id, props))
    return on_create(event)


def on_delete(event: json):
    physical_id = event["PhysicalResourceId"]
    logger.info("delete resource %s" % physical_id)

    # delete role for pipeline
    path = '_opendistro/_security/api/roles/pipeline_role'
    response = send_to_os('DELETE', path)
    if not response.ok:
        raise Exception(f'Error {response.status_code} in deleting the pipeline role: {response.text}')

    # delete the role mapping for pipeline
    path = '_opendistro/_security/api/rolesmapping/pipeline_role'
    response = send_to_os('DELETE', path)
    if not response.ok:
        raise Exception(f'Error {response.status_code} in deleting the pipeline role mapping: {response.text}')

    # delete the user for dashboard
    user('DELETE', secret_arn=admin_secret_arn)

    # delete the readonly user for dashboard
    user('DELETE', secret_arn=user_secret_arn)

    # delete index template for spark logs
    index_template('spark_logs', 'DELETE')

    # delete the index template for spark task metrics
    index_template('spark_task_metrics', 'DELETE')

    # delete the index template for spark stage agg metrics
    index_template('spark_stage_agg_metrics', 'DELETE')

    # delete the data skew dashboard
    logger.info(f'Deleting saved objects')
    resources = event['Data']['Resources']
    for r in resources:
        response = saved_objects(name='nested', action='DELETE', type=r['type'], id=r['id'])