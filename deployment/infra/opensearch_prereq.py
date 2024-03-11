# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0


from aws_cdk import (
    Stack, RemovalPolicy, )
from aws_cdk.aws_ec2 import SecurityGroup, SubnetSelection
from aws_cdk.aws_iam import CfnServiceLinkedRole, ServicePrincipal, \
    Role
from aws_cdk.aws_kms import Key
from aws_cdk.aws_logs import LogGroup, RetentionDays
from constructs import Construct

from aws_cdk.aws_ec2 import IVpc, ISubnet


class OpensearchPreReq(Construct):

    @property
    def domain_key(self):
        return self.__domain_key
    
    @property
    def domain_log_group(self):
        return self.__domain_log_group
    
    @property
    def domain_security_group(self):
        return self.__domain_security_group
    
    @property
    def domain_name(self):
        return self.__domain_name
    
    @property
    def domain_log_group(self):
        return self.__domain_log_group

    @property
    def domain_vpc(self):
        return self.__vpc

    @property
    def domain_subnets(self):
        return self.__subnets
    
    @property
    def domain_admin_role(self):
        return self.__role
            
    def __init__(self,
                 scope: Construct, 
                 id: str,
                 vpc: IVpc,
                 subnets: SubnetSelection,
                 **kwargs):
        super().__init__(scope, id, **kwargs)
        
        # Stack, needed to get region and account ID
        stack = Stack.of(self)

        self.__domain_name = 'spark-observability'
        domain_log_group_name='spark-observability-logs'

        # assumed by lambda because we are using a customer resource to configure the cluster via Opensearch API
        self.__role = Role(self, 'Role',
                           assumed_by=ServicePrincipal('lambda.amazonaws.com'),
                           )

        # KMS key used to encrypt the data at rest in Opensearch
        self.__domain_key = Key(self, 'Key',
                  enable_key_rotation=True,
                  removal_policy=RemovalPolicy.DESTROY,
                  )

        # Log group for the Opensearch domain
        self.__domain_log_group = LogGroup(self, 'OpensearchLogGroup',
                             removal_policy=RemovalPolicy.DESTROY,
                             retention=RetentionDays.ONE_WEEK,
                             log_group_name=domain_log_group_name,
                             )
        self.__domain_log_group.grant_write(ServicePrincipal("es.amazonaws.com"))

        # Security group for the Opensearch domain
        self.__domain_security_group = SecurityGroup(
            self, "DomainSecurityGroup",
            vpc=vpc,
            disable_inline_rules=True,
        )
        self.__vpc = vpc
        self.__subnets = subnets
        
        # Service Linked role for Amazon Opensearch
        try:
            Role.from_role_name(self, 'OpensearchSlr', 'AWSServiceRoleForAmazonOpenSearchService')
        except:
            CfnServiceLinkedRole(self, 'ServiceLinkedRole', aws_service_name='es.amazonaws.com')