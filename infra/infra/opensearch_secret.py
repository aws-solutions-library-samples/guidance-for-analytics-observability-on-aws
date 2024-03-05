# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json


from aws_cdk import (
    Duration, )
from aws_cdk.aws_lambda import Function
from aws_cdk.aws_secretsmanager import Secret, SecretStringGenerator
from constructs import Construct
from infra.opensearch_cr_helpers import OpensearchCrHelpers


class OpensearchSecret(Construct):

    @property
    def secret(self):
        return self.__secret
        
    def __init__(self, scope: Construct, id: str, 
                 user_name: str, 
                 helper: OpensearchCrHelpers,
                 rotate_function: Function,
                 **kwargs
                 ) -> None:
        super().__init__(scope, id, **kwargs)

        self.__secret = Secret(self, 'Secret',
                        generate_secret_string=SecretStringGenerator(
                            secret_string_template=json.dumps({'username': user_name}),
                            generate_string_key='password',
                            exclude_characters='"@\\/'
                        ))

        self.__secret.add_rotation_schedule('Rotation', 
                                            automatically_after=Duration.days(30),
                                            rotation_lambda=rotate_function,
                                            rotate_immediately_on_update=False,
                                            )
        
        self.__secret.grant_read(helper.role)