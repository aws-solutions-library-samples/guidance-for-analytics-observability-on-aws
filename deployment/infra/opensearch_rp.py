# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0



from pathlib import Path
import re
from aws_cdk import (
    Duration, RemovalPolicy, Stack, Tags, )
from aws_cdk.aws_autoscaling import AutoScalingGroup, BlockDevice, BlockDeviceVolume, EbsDeviceVolumeType, Signals, NotificationConfiguration
from aws_cdk.aws_ec2 import SecurityGroup, Port, Peer, IVpc, AmazonLinuxImage, \
    SubnetSelection, InstanceType, InstanceClass, InstanceSize, AmazonLinuxGeneration, AmazonLinuxEdition, AmazonLinuxVirt, AmazonLinuxStorage
from aws_cdk.aws_iam import InstanceProfile, ManagedPolicy, ServicePrincipal, \
    Role, PolicyDocument, Effect
from aws_cdk.aws_opensearchservice import CfnDomain
from aws_cdk.aws_sns import Topic
from aws_cdk.aws_kms import Key
from constructs import Construct
import io
from aws_cdk.aws_iam import PolicyStatement



class OpensearchRp(Construct):

    ami = AmazonLinuxImage(
        generation=AmazonLinuxGeneration.AMAZON_LINUX_2,
        storage=AmazonLinuxStorage.GENERAL_PURPOSE,
    )

    @property
    def role(self):
        return self.__role
    
    @property
    def security_group(self):
        return self.__security_group
    
    @property
    def autoscaling_group(self):
        return self.__autoscaling_group
        
    def __init__(self, scope: Construct, id: str, 
                 domain: CfnDomain,
                 vpc: IVpc,
                 subnets: SubnetSelection,
                 **kwargs
                 ) -> None:
        super().__init__(scope, id, **kwargs)

        # Stack, needed to get region and account ID
        stack = Stack.of(self)

        # Managed policy for SSM Access
        ssm_policy = ManagedPolicy(self, 'SsmPolicy', 
                                   document=PolicyDocument(
                                       statements=[
                                            PolicyStatement(
                                                effect=Effect.ALLOW,
                                                actions=[
                                                    "ssm:DescribeAssociation",
                                                    "ssm:GetDeployablePatchSnapshotForInstance",
                                                    "ssm:GetDocument",
                                                    "ssm:DescribeDocument",
                                                    "ssm:GetManifest",
                                                    "ssm:GetParameter",
                                                    "ssm:GetParameters",
                                                    "ssm:ListAssociations",
                                                    "ssm:ListInstanceAssociations",
                                                    "ssm:PutInventory",
                                                    "ssm:PutComplianceItems",
                                                    "ssm:PutConfigurePackageResult",
                                                    "ssm:UpdateAssociationStatus",
                                                    "ssm:UpdateInstanceAssociationStatus",
                                                    "ssm:UpdateInstanceInformation"
                                                ],
                                                resources=["*"],
                                            ),
                                            PolicyStatement(
                                                effect=Effect.ALLOW,
                                                actions=[
                                                    "ssmmessages:CreateControlChannel",
                                                    "ssmmessages:CreateDataChannel",
                                                    "ssmmessages:OpenControlChannel",
                                                    "ssmmessages:OpenDataChannel"
                                                ],
                                                resources=["*"],
                                            ),
                                            PolicyStatement(
                                                effect=Effect.ALLOW,
                                                actions=[
                                                "ec2messages:AcknowledgeMessage",
                                                "ec2messages:DeleteMessage",
                                                "ec2messages:FailMessage",
                                                "ec2messages:GetEndpoint",
                                                "ec2messages:GetMessages",
                                                "ec2messages:SendReply"
                                                ],
                                                resources=["*"],
                                            )
                                       ]
                                   ))

    
        # IAM Role
        self.__role = Role(self, "RpIamRole",
                       assumed_by=ServicePrincipal("ec2.amazonaws.com"),
                       managed_policies=[
                           ssm_policy
                       ])

        # Reverse Proxy Security Group
        self.__security_group = SecurityGroup(self, "RpSecurityGroup",
                                                vpc=vpc,
                                                )
        
        self.__security_group.add_ingress_rule(
            peer=Peer.ipv4("0.0.0.0/0"),
            connection=Port.tcp(443)
        )
        
        sns_key = Key(self, 'SnsKey',
                      enabled=True,
                      pending_window=Duration.days(7),
                      enable_key_rotation=True,
                      removal_policy=RemovalPolicy.DESTROY,
                      )

        # SNS topic for scaling events of the ASG
        topic = Topic(self, "SnsTopic", master_key=sns_key)

        # Reverse Proxy Auto Scaling Group        
        self.__autoscaling_group = AutoScalingGroup(self, 'AutoScalingGroup',
                                                    instance_type=InstanceType.of(InstanceClass.BURSTABLE3, InstanceSize.MICRO),
                                                    role=self.__role,
                                                    min_capacity=1,
                                                    max_capacity=1,
                                                    block_devices=[
                                                        BlockDevice(
                                                            device_name="/dev/sda1",
                                                            volume=BlockDeviceVolume.ebs(15,
                                                                delete_on_termination=True,
                                                                volume_type=EbsDeviceVolumeType.GP3,
                                                                throughput=125,
                                                                encrypted=True
                                                            )
                                                        )
                                                    ], 
                                                    machine_image=self.ami,
                                                    vpc=vpc,
                                                    vpc_subnets=subnets,
                                                    security_group=self.__security_group,
                                                    notifications=[
                                                        NotificationConfiguration(
                                                            topic=topic
                                                        )
                                                    ])
        Tags.of(self.__autoscaling_group).add('SparkObservability', 'true')
        
        with io.open(Path(__file__).parent.joinpath('./resources/reverse-proxy/user-data.sh'), mode='r', encoding='utf8') as f:
            script = f.read()

            bootscript = re.sub(r"{domain_endpoint}", domain.get_att('DomainEndpoint').to_string(), script)

        self.__autoscaling_group.add_user_data(bootscript)