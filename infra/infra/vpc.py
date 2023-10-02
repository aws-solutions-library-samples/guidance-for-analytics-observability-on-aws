from aws_cdk import Stack, CfnOutput
from aws_cdk.aws_ec2 import Vpc
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
