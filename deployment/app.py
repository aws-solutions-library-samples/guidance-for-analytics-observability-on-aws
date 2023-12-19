#!/usr/bin/env python3

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os

import aws_cdk as cdk

from infra.backend_stack import BackendStack
from infra.emr_serverless_stack import EmrServerlessStack
from infra.ingestor_stack import IngestorStack
from infra.vpc import VpcStack

app = cdk.App()

account = os.getenv('AWS_ACCOUNT_ID')
if account is None:
    raise Exception("AWS_ACCOUNT_ID environment variable must be set")

region = os.getenv('AWS_REGION')
if region is None:
    raise Exception("AWS_REGION environment variable must be set")

if app.node.try_get_context('Stack') == 'backend':
    backend = BackendStack(app, "BackendStack",
                           env=cdk.Environment(
                               account=account,
                               region=region,
                           )
                           # If you don't specify 'env', the VPC will be created with only 2 AZs instead dof 3 AZs.
                           )

elif app.node.try_get_context('Stack') == 'ingestor':

    IngestorStack(app, 'IngestorStack',
                  env=cdk.Environment(
                      account=account,
                      region=region,
                  ))

elif app.node.try_get_context('Stack') == 'vpc':

    VpcStack(app, 'VpcStack',
             env=cdk.Environment(
                 account=account,
                 region=region,
             ))

elif app.node.try_get_context('Stack') == 'example':

    EmrServerlessStack(app, 'EmrServerlessExampleStack',
                       env=cdk.Environment(
                           account=account,
                           region=region,
                       ))
else:
    raise Exception("Stack parameter must be 'backend', 'vpc', 'ingestor' or 'example'")
app.synth()
