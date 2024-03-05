# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import logging
import os
from requests_aws4auth import AWS4Auth
import requests
from opensearchpy import AWSV4SignerAuth
from botocore.exceptions import ClientError
import base64
import json



logger = logging.getLogger()
logger.setLevel(logging.INFO)
host = os.environ['DOMAIN_ENDPOINT']
domain_name = os.environ['DOMAIN_NAME']
region = os.environ['AWS_REGION']
credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(credentials, region)

session = requests.Session()
ssm_client = boto3.client('secretsmanager', endpoint_url=os.environ['SECRETS_MANAGER_ENDPOINT'])
os_client = boto3.client('opensearch')
awsauth = AWS4Auth(credentials.access_key,
                credentials.secret_key,
                region,
                'es',
                session_token=credentials.token)



def get_secret(secret_arn: str):
    ssm_client = boto3.client('secretsmanager', endpoint_url=os.environ['SECRETS_MANAGER_ENDPOINT'])
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
    elif action == 'PATCH':
        r = session.patch(url, auth=awsauth, json=payload, headers=headers)
    else:
        raise Exception('HTTP action not supported')
    logger.info(r.text)
    return r


def lambda_handler(event, context):
    """Secrets Manager Rotation Template

    This is a template for creating an AWS Secrets Manager rotation lambda

    Args:
        event (dict): Lambda dictionary of event parameters. These keys must include the following:
            - SecretId: The secret ARN or identifier
            - ClientRequestToken: The ClientRequestToken of the secret version
            - Step: The rotation step (one of createSecret, setSecret, testSecret, or finishSecret)

        context (LambdaContext): The Lambda runtime information

    Raises:
        ResourceNotFoundException: If the secret with the specified arn and stage does not exist

        ValueError: If the secret is not properly configured for rotation

        KeyError: If the event parameters do not contain the expected keys

    """
    arn = event['SecretId']
    token = event['ClientRequestToken']
    step = event['Step']

    # Make sure the version is staged correctly
    metadata = ssm_client.describe_secret(SecretId=arn)
    if not metadata['RotationEnabled']:
        logger.error("Secret %s is not enabled for rotation" % arn)
        raise ValueError("Secret %s is not enabled for rotation" % arn)
    versions = metadata['VersionIdsToStages']
    if token not in versions:
        logger.error("Secret version %s has no stage for rotation of secret %s." % (token, arn))
        raise ValueError("Secret version %s has no stage for rotation of secret %s." % (token, arn))
    if "AWSCURRENT" in versions[token]:
        logger.info("Secret version %s already set as AWSCURRENT for secret %s." % (token, arn))
        return
    elif "AWSPENDING" not in versions[token]:
        logger.error("Secret version %s not set as AWSPENDING for rotation of secret %s." % (token, arn))
        raise ValueError("Secret version %s not set as AWSPENDING for rotation of secret %s." % (token, arn))

    if step == "createSecret":
        create_secret(ssm_client, arn, token)

    elif step == "setSecret":
        set_secret(ssm_client, arn, token)

    elif step == "testSecret":
        test_secret(ssm_client, arn, token)

    elif step == "finishSecret":
        finish_secret(ssm_client, arn, token)

    else:
        raise ValueError("Invalid step parameter")


def create_secret(ssm_client, arn, token):
    """Create the secret

    This method first checks for the existence of a secret for the passed in token. If one does not exist, it will generate a
    new secret and put it with the passed in token.

    Args:
        ssm_client (client): The secrets manager service client

        arn (string): The secret ARN or other identifier

        token (string): The ClientRequestToken associated with the secret version

    Raises:
        ResourceNotFoundException: If the secret with the specified arn and stage does not exist

    """
    # Make sure the current secret exists
    ssm_client.get_secret_value(SecretId=arn, VersionStage="AWSCURRENT")

    # Now try to get the secret version, if that fails, put a new secret
    try:
        ssm_client.get_secret_value(SecretId=arn, VersionId=token, VersionStage="AWSPENDING")
        logger.info("createSecret: Successfully retrieved secret for %s." % arn)
    except ssm_client.exceptions.ResourceNotFoundException:
        # Get exclude characters from environment variable
        exclude_characters = os.environ['EXCLUDE_CHARACTERS'] if 'EXCLUDE_CHARACTERS' in os.environ else '/@"\'\\'
        # Generate a random password
        passwd = ssm_client.get_random_password(ExcludeCharacters=exclude_characters)

        # Put the secret
        ssm_client.put_secret_value(SecretId=arn, ClientRequestToken=token, SecretString=passwd['RandomPassword'], VersionStages=['AWSPENDING'])
        logger.info("createSecret: Successfully put secret for ARN %s and version %s." % (arn, token))

    
def set_secret(arn, token):
    """Set the secret

    This method should set the AWSPENDING secret in the service that the secret belongs to. For example, if the secret is a database
    credential, this method should take the value of the AWSPENDING secret and set the user's password to this value in the database.

    Args:
        ssm_client (client): The secrets manager service client

        arn (string): The secret ARN or other identifier

        token (string): The ClientRequestToken associated with the secret version

    """
    secret = get_secret(arn)
    # Get the current user
    response = send_to_os('PATCH', f"_plugins/_security/api/internalusers/{secret['username']}")
    payload =f'[{"op": "replace", "path": "/password", "value": {secret["password"]}} ]'
    if not response.ok:
        raise Exception(f'Error {response.status_code} in rotation {secret["username"]} password: {response.text}')
    

def test_secret(arn, token):
    """Test the secret

    This method should validate that the AWSPENDING secret works in the service that the secret belongs to. For example, if the secret
    is a database credential, this method should validate that the user can login with the password in AWSPENDING and that the user has
    all of the expected permissions against the database.

    If the test fails, this function should raise an exception. (Any exception.)
    If no exception is raised, the test is considered to have passed. (The return value is ignored.)

    Args:
        ssm_client (client): The secrets manager service client

        arn (string): The secret ARN or other identifier

        token (string): The ClientRequestToken associated with the secret version

    """
    logger.info("No test secret to run for " % arn)


def finish_secret(arn, token):
    """Finish the secret

    This method finalizes the rotation process by marking the secret version passed in as the AWSCURRENT secret.

    Args:
        ssm_client (client): The secrets manager service client

        arn (string): The secret ARN or other identifier

        token (string): The ClientRequestToken associated with the secret version

    Raises:
        ResourceNotFoundException: If the secret with the specified arn does not exist

    """
    # First describe the secret to get the current version
    metadata = ssm_client.describe_secret(SecretId=arn)
    current_version = None
    for version in metadata["VersionIdsToStages"]:
        if "AWSCURRENT" in metadata["VersionIdsToStages"][version]:
            if version == token:
                # The correct version is already marked as current, return
                logger.info("finishSecret: Version %s already marked as AWSCURRENT for %s" % (version, arn))
                return
            current_version = version
            break

    # Finalize by staging the secret version current
    ssm_client.update_secret_version_stage(SecretId=arn, VersionStage="AWSCURRENT", MoveToVersionId=token, RemoveFromVersionId=current_version)
    logger.info("finishSecret: Successfully set AWSCURRENT stage to version %s for secret %s." % (token, arn))