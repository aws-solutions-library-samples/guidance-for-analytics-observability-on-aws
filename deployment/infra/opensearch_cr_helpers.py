# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0



from aws_cdk import (
    Aws, )
from aws_cdk.aws_ec2 import SecurityGroup
from aws_cdk.aws_iam import ManagedPolicy, PolicyStatement, PolicyDocument, Effect
from constructs import Construct
from infra.opensearch_prereq import OpensearchPreReq


class OpensearchCrHelpers(Construct):

    @property
    def managed_policy(self):
        return self.__managed_policy

    @property
    def role(self):
        return self.__role
    
    @property
    def vpc(self):
        return self.__vpc
    
    @property
    def subnets(self):
        return self.__subnets
    
    @property
    def security_group(self):
        return self.__security_group
    
    @property
    def domain_name(self):
        return self.__domain_name
    
    @property
    def function_name(self):
        return self.__function_name
        
    def __init__(self, scope: Construct, id: str, function_name: str, prereq: OpensearchPreReq, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # policy to write lambda logs to CloudWatch Logs
        self.__managed_policy = ManagedPolicy(self, 'LogsManagedPolicy',
                               document=PolicyDocument(
                                   statements=[
                                       PolicyStatement(
                                            actions=[
                                                "logs:CreateLogGroup",
                                                "logs:CreateLogStream",
                                                "logs:PutLogEvents"
                                            ],
                                            resources=[
                                                f'arn:aws:logs:{Aws.REGION}:{Aws.ACCOUNT_ID}:log-group:/aws/lambda/{function_name}',
                                                f'arn:aws:logs:{Aws.REGION}:{Aws.ACCOUNT_ID}:log-group:/aws/lambda/{function_name}:log-stream:*',    
                                            ],
                                            effect=Effect.ALLOW,
                                        )
                                   ])   
                               )

        # add permission to update the cluster after creation. required to enable FGAC with internal database users
        prereq.domain_admin_role.add_to_policy(
            PolicyStatement(
                actions=['es:UpdateElasticsearchDomainConfig'],
                resources=[f'arn:aws:es:{Aws.REGION}:{Aws.ACCOUNT_ID}:domain/{prereq.domain_name}'],
            ))
        
        # add permissions to manage ENI for interacting with Opensearch in private subnets
        prereq.domain_admin_role.add_to_policy(
            PolicyStatement(
                actions=[
                    'ec2:CreateNetworkInterface',
                    'ec2:DescribeNetworkInterfaces',
                    'ec2:DeleteNetworkInterface',

                ],
                resources=['*'],
            ))
        
        prereq.domain_admin_role.add_to_policy(PolicyStatement(
            resources=[prereq.domain_key.key_arn],
            actions=['kms:DescribeKey'],
        ))

        prereq.domain_admin_role.add_managed_policy(self.__managed_policy)
        
        # the security group for the CR
        self.__security_group = SecurityGroup(self, 'SecurityGroup', vpc=prereq.domain_vpc)
        self.__function_name = function_name
        self.__role = prereq.domain_admin_role
        self.__domain_name = prereq.domain_name
        self.__vpc = prereq.domain_vpc
        self.__subnets = prereq.domain_subnets