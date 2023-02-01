from aws_cdk import (
    Stack, RemovalPolicy, Aws, CfnJson, CfnOutput,
)
from aws_cdk.aws_cognito import UserPool, CognitoDomainOptions, CfnUserPoolGroup, AutoVerifiedAttrs, StandardAttributes, \
    StandardAttribute, CfnIdentityPool, CfnIdentityPoolRoleAttachment
from aws_cdk.aws_ec2 import Vpc, SubnetType, EbsDeviceVolumeType, SubnetSelection
from aws_cdk.aws_iam import CfnServiceLinkedRole, Role, ServicePrincipal, ManagedPolicy, FederatedPrincipal, \
    PolicyStatement, AnyPrincipal
from aws_cdk.aws_kms import Key
from aws_cdk.aws_logs import LogGroup, RetentionDays
from aws_cdk.aws_opensearchservice import Domain, EngineVersion, CapacityConfig, ZoneAwarenessConfig, \
    EncryptionAtRestOptions, EbsOptions, CognitoOptions, AdvancedSecurityOptions, LoggingOptions
from aws_cdk.custom_resources import AwsCustomResource, AwsCustomResourcePolicy, AwsSdkCall
from constructs import Construct
from aws_cdk.aws_cognito_identitypool_alpha import IdentityPool, IdentityPoolAuthenticationProviders, \
    IdentityPoolRoleMapping, IdentityPoolProviderUrl, UserPoolAuthenticationProvider


class InfraStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        slr = CfnServiceLinkedRole(self, 'ServiceLinkedRole', aws_service_name='es.amazonaws.com')

        # Create a default VPC with 3 AZs
        # You need to set the env variables in the app.py to get effectively 3 AZs, otherwise you only get 2
        # vpc = Vpc(self, 'Vpc', max_azs=3)

        # KMS key used to encrypt the data at rest in Opensearch
        key = Key(self, 'Key',
                  enable_key_rotation=True,
                  removal_policy=RemovalPolicy.DESTROY,
                  )

        # IAM Role assumed Opensearch to interact with Cognito
        domain_role = Role(self, 'Role',
                           assumed_by=ServicePrincipal('es.amazonaws.com'),
                           managed_policies=[ManagedPolicy.from_aws_managed_policy_name('AmazonOpenSearchServiceCognitoAccess')],
                           )

        # Cognito User pool containing all the users able to interact with Opensearch
        user_pool = UserPool(self, 'UserPool',
                             removal_policy=RemovalPolicy.DESTROY,
                             sign_in_case_sensitive=False,
                             auto_verify=AutoVerifiedAttrs(email=True),
                             standard_attributes=StandardAttributes(
                                 email=StandardAttribute(
                                     mutable=False,
                                     required=True,
                                 )
                             ))

        # Congito domain for the Opensearch sign-in
        user_pool.add_domain('CognitoDomain', cognito_domain=CognitoDomainOptions(domain_prefix='spark-observability'))

        # Cognito identity pool. Will contain the mapping between users and roles
        identity_pool = IdentityPool(self, 'IdentityPool',
                                     authentication_providers=IdentityPoolAuthenticationProviders(
                                        user_pools=[UserPoolAuthenticationProvider(user_pool=user_pool)]
                                     ))

        # Conditions that are commons to thd IAM role used by Cognito users groups (admin or readonly)
        roles_conditions = {
            "StringEquals": {
                "cognito-identity.amazonaws.com:aud": CfnJson(scope=self, id='IdentityRef', value=identity_pool.identity_pool_id)
            },
            "ForAnyValue:StringLike": {
                "cognito-identity.amazonaws.com:amr": "authenticated"
            }
        }

        # IAM Role used by Cognito admin users group
        admin_role = Role(self, 'OpensearchAdminRole',
                          assumed_by=FederatedPrincipal('cognito-identity.amazonaws.com').with_conditions(roles_conditions)
                          )

        # IAM Role used by Cognito readonly users group
        readonly_role = Role(self, 'OpensearchReadonlyRole',
                          assumed_by=FederatedPrincipal('cognito-identity.amazonaws.com').with_conditions(roles_conditions)
                          )

        # Cognito admin users group
        user_pool_group = CfnUserPoolGroup(self, 'AdminPoolGroup',
                                           user_pool_id=user_pool.user_pool_id,
                                           group_name='opensearch-admin',
                                           role_arn=admin_role.role_arn,
                                           )

        log_group = LogGroup(self, 'OpensearchLogGroup',
                             removal_policy=RemovalPolicy.DESTROY,
                             retention=RetentionDays.ONE_WEEK,
                             log_group_name='spark-observability-logs',
                             )

        domain = Domain(self, 'Domain',
                        version=EngineVersion.OPENSEARCH_2_3,
                        removal_policy=RemovalPolicy.DESTROY,
                        enable_version_upgrade=True,
                        enforce_https=True,
                        encryption_at_rest=EncryptionAtRestOptions(
                            enabled=True,
                            kms_key=key,
                        ),
                        node_to_node_encryption=True,
                        # vpc=vpc,
                        # vpc_subnets=[SubnetSelection(
                        #     subnet_type=SubnetType.PRIVATE_WITH_EGRESS,
                        #     one_per_az=True,
                        # )],
                        zone_awareness=ZoneAwarenessConfig(
                            availability_zone_count=3
                        ),
                        # TODO create T-shirt sizing
                        capacity=CapacityConfig(
                            master_nodes=3,
                            master_node_instance_type='m6g.large.search',
                            data_nodes=3,
                            data_node_instance_type='r6gd.large.search',
                            warm_nodes=2,
                            warm_instance_type='ultrawarm1.medium.search',
                        ),
                        ebs=EbsOptions(
                            enabled=False,
                            # volume_type=EbsDeviceVolumeType.GP3,
                        ),
                        cognito_dashboards_auth=CognitoOptions(
                            identity_pool_id=identity_pool.identity_pool_id,
                            user_pool_id=user_pool.user_pool_id,
                            role=domain_role,
                        ),
                        fine_grained_access_control=AdvancedSecurityOptions(master_user_arn=admin_role.role_arn),
                        logging=LoggingOptions(
                            app_log_group=log_group,
                            app_log_enabled=True,
                            audit_log_group=log_group,
                            audit_log_enabled=True,
                        )
                        )

        domain.grant_read_write(AnyPrincipal())

        admin_policy = ManagedPolicy(self, 'OpensearchAdminPolicy',
                                     roles=[admin_role],
                                     statements=[
                                         PolicyStatement(
                                             resources=[domain.domain_arn],
                                             actions=['es:ESHttpPost', 'es:ESHttpGet', 'es:ESHttpPut'],
                                         )
                                     ])

        # user_pool_clients = AwsCustomResource(self, 'ClientIdCr',
        #                                       policy=AwsCustomResourcePolicy.from_sdk_calls(resources=[user_pool.user_pool_arn]),
        #                                       on_create=AwsSdkCall(
        #                                           service='CognitoIdentityServiceProvider',
        #                                           action='listUserPoolClients',
        #                                           parameters={
        #                                               'UserPoolId': user_pool.user_pool_id,
        #                                           },
        #                                       ))
        # user_pool_clients.node.add_dependency(domain)
        #
        # CfnIdentityPoolRoleAttachment(self, 'UserPoolRoleAttachment',
        #                               identity_pool_id=identity_pool.ref,
        #                               roles={
        #                                   'authenticated': readonly_role.roleArn,
        #                               },
        #                               role_mappings=CfnJson(scope=self, id='RoleMappingJson',
        #                                                     value={
        #                                                         f'{user_pool.user_pool_provider_url}'
        #                                                     })
        #                               )

        CfnOutput(self, 'CreateUserUrl',
                  description='URL to create new users. Add the user to admin group',
                  value="https://" + Aws.REGION + ".console.aws.amazon.com/cognito/users?region=" + Aws.REGION + "#/pool/" + user_pool.user_pool_id + "/users"
                  )

        CfnOutput(self, 'OpensearchDashboardUrl',
                  description='Opensearch Dashboard URL',
                  value='https://' + domain.domain_endpoint +'/_dashboards'
                  )