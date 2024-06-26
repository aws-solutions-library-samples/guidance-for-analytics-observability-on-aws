# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import Aspects, Stack, CfnOutput
from aws_cdk.aws_ec2 import Vpc
from cdk_nag import AwsSolutionsChecks, NagSuppressions
from constructs import Construct


class VpcStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = Vpc(self, 'Vpc',
                  max_azs=1,
                  nat_gateways=1,
                  )

        CfnOutput(self, 'VpcID',
                  description='VPC ID for the EMR Serverless example',
                  value=vpc.vpc_id,
                  )

        Aspects.of(self).add(AwsSolutionsChecks())
        NagSuppressions.add_resource_suppressions_by_path(stack=self, path='/VpcStack/Vpc/Resource', suppressions=[
            {"id": "AwsSolutions-VPC7", "reason": "VPC is provided only for testing"},
        ])