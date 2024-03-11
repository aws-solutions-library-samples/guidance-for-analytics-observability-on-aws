# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0



from aws_cdk import (
    Aws, Stack, Duration, CustomResource)
from aws_cdk.aws_logs import RetentionDays
from aws_cdk.custom_resources import Provider
from aws_cdk.aws_autoscaling import CfnAutoScalingGroup
from aws_cdk.aws_ec2 import IVpc, ISubnet
from aws_cdk.aws_iam import PolicyStatement, ServicePrincipal, \
    Role, PolicyDocument
from aws_cdk.aws_lambda import Code, Runtime, Function
from aws_cdk.aws_opensearchservice import CfnDomain
from constructs import Construct




class OpensearchRpCr(Construct):
    
    @property
    def custom_resource(self):
        return self.__custom_resource
        
    def __init__(self, scope: Construct, id: str, 
                 asg: CfnAutoScalingGroup,
                 **kwargs
                 ) -> None:
        super().__init__(scope, id, **kwargs)

        # Stack, needed to get region and account ID
        stack = Stack.of(self)

        # Lambda function to retrieve the public IP of the NGINX proxy
        lambda_name = 'eip-finder'

        # IAM role for Lambda function
        lambda_role = Role(self, "LambdaRole",
                           assumed_by=ServicePrincipal("lambda.amazonaws.com"),
                           path="/",
                           inline_policies={
                               "lambda-logs": PolicyDocument(
                                   statements=[
                                       PolicyStatement(
                                           actions=[
                                               "ec2:Describe*",
                                               "ec2:List*"
                                           ],
                                           resources=["*"],
                                       ),
                                       PolicyStatement(
                                           actions=[
                                               "logs:CreateLogGroup",
                                               "logs:CreateLogStream",
                                               "logs:PutLogEvents"
                                           ],
                                           resources=[
                                                f'arn:aws:logs:{Aws.REGION}:{Aws.ACCOUNT_ID}:log-group:/aws/lambda/{lambda_name}',
                                                f'arn:aws:logs:{Aws.REGION}:{Aws.ACCOUNT_ID}:log-group:/aws/lambda/{lambda_name}:log-stream:*',      
                                            ]
                                       )
                                   ]
                               )
                           })

        lambda_function = Function(self, "GetEC2PublicIP",
                                   function_name=lambda_name,
                                   code=Code.from_inline("""
import json
import boto3
import logging
import urllib3
import time
http = urllib3.PoolManager()

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)

SUCCESS = "SUCCESS"
FAILED = "FAILED"
time.sleep(30)

def lambda_handler(event, context):
    global arn
    logger.info('Event: %s' % json.dumps(event))
    responseData={}
    try:
        if event['RequestType'] == 'Create' or event['RequestType'] == 'Update':
            print("Request Type:",event['RequestType'])
            client = boto3.client('ec2')
            PublicIpAddress = ''
            response = client.describe_instances(
                Filters=[ {
                        'Name': 'tag:SparkObservability',
                        'Values': ['true']}
                ]
            )
            for r in response['Reservations']:
                for i in r['Instances']:
                    PublicIpAddress = (i['PublicIpAddress'])
                    print (PublicIpAddress)

            responseData={'PublicIpAddress': PublicIpAddress}
            print(responseData)
        responseStatus = 'SUCCESS'
    except Exception as e:
        print('Failed to process:', e)
        responseStatus = 'FAILURE'
        responseData = {'Failure': 'Check Logs.'}
    return { 'Data': responseData }
"""),
                                   handler="index.lambda_handler",
                                   runtime=Runtime.PYTHON_3_11,
                                   timeout=Duration.seconds(120),
                                   role=lambda_role
                                   )
        # Custom resource provider
        provider = Provider(self, "Provider",
            on_event_handler=lambda_function,
            log_retention=RetentionDays.ONE_DAY,
        )

        # Custom resource
        self.__custom_resource = CustomResource(
            self, "LambdaTrigger",
            service_token=provider.service_token,
        )
        self.__custom_resource.node.add_dependency(asg)

        # Dependencies
        lambda_role.node.add_dependency(asg)
        self.__custom_resource.node.add_dependency(lambda_role)