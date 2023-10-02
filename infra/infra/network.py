from aws_cdk.aws_ec2 import SubnetType, Vpc
from constructs import Construct


class Network:
    def getSubnets(scope: Construct, az_count: int) -> [str]:
        subnets = scope.node.try_get_context("SubnetsIDs")
        if subnets is None:
            # Create a default VPC with 3 AZs
            # You need to set the env variables in the app.py to get effectively 3 AZs, otherwise you only get 2
            vpc = Vpc(scope, 'Vpc', max_azs=3)
            return vpc.select_subnets(one_per_az=True, subnet_type=SubnetType.PRIVATE_WITH_EGRESS).subnet_ids[:az_count]
        else:
            try:
                return subnets.split(',')
            except:
                raise Exception("SubnetsIDs parameter cannot be parsed. Provide Subnets IDs in a list with comma separation")