# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import subprocess
from pathlib import Path


from aws_cdk import (
    Duration, CustomResource, )
from aws_cdk.aws_lambda import LayerVersion, Code, Runtime, Function
from aws_cdk.custom_resources import Provider
from constructs import Construct
from aws_cdk.aws_secretsmanager import ISecret
from aws_cdk.aws_opensearchservice import CfnDomain
from aws_cdk.aws_iam import IRole

from infra.opensearch_cr_helpers import OpensearchCrHelpers

class OpensearchBootstrap(Construct):

    def __init__(self, scope: Construct, id: str, 
                 opensearch_cr_helpers: OpensearchCrHelpers,
                 domain: CfnDomain,
                 layer: LayerVersion,
                 user_secret: ISecret,
                 admin_secret: ISecret,
                 pipeline_role: IRole,
                 **kwargs) -> None:
        super().__init__(scope, id, **kwargs)


        bootstrap_lambda = Function(scope=self,
                                    id='OsBootstrapFunction',
                                    function_name=opensearch_cr_helpers.function_name,
                                    runtime=Runtime.PYTHON_3_11,
                                    code=Code.from_asset(
                                        str(Path(__file__).parent.joinpath('resources/lambda/opensearch-bootstrap'))),
                                    handler='bootstrap.on_event',
                                    environment={'PIPELINE_ROLE_ARN': pipeline_role.role_arn,
                                                 'DOMAIN_ENDPOINT': domain.get_att('DomainEndpoint').to_string(),
                                                 'DOMAIN_NAME': opensearch_cr_helpers.domain_name,
                                                 'USER_SECRET_ARN': user_secret.secret_arn,
                                                 'ADMIN_SECRET_ARN': admin_secret.secret_arn,
                                                 },
                                    layers=[layer],
                                    timeout=Duration.minutes(15),
                                    role=opensearch_cr_helpers.role,
                                    vpc=opensearch_cr_helpers.vpc,
                                    vpc_subnets=opensearch_cr_helpers.subnets,
                                    security_groups=[opensearch_cr_helpers.security_group]
                                    )

        bootstrap_lambda_provider = Provider(scope=self,
                                             id='BootstrapLambdaProvider',
                                             on_event_handler=bootstrap_lambda
                                             )
        os_bootstrap = CustomResource(scope=self,
                                      id='ExecuteOsBootstrap',
                                      service_token=bootstrap_lambda_provider.service_token,
                                      properties={'Timeout': 900}
                                      )
        os_bootstrap.node.add_dependency(domain)
