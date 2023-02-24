from enum import Enum
from typing import Optional

from aws_cdk.aws_opensearchservice import CfnDomain
from aws_cdk.aws_secretsmanager import Secret
from constructs import Construct


class AuthMode(Enum):
    BASIC_AUTH = 'basic_auth'
    SAML = 'saml'


class SecurityOptions(Construct):

    def __init__(self, scope: Construct, construct_id: str, auth_mode: AuthMode, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if auth_mode == AuthMode.BASIC_AUTH:
            self._secret = Secret(self, 'OpensearchDomainAdminSecret')

            self._config = CfnDomain.AdvancedSecurityOptionsInputProperty(
                enabled=True,
                internal_user_database_enabled=True,
                master_user_options=CfnDomain.MasterUserOptionsProperty(
                    master_user_name="admin",
                    master_user_password=self._secret.secret_value.unsafe_unwrap()
                )
            )
        else:
            self._config = CfnDomain.AdvancedSecurityOptionsInputProperty(
                enabled=True,
                internal_user_database_enabled=False,
                saml_options=CfnDomain.SAMLOptionsProperty(
                    enabled=False,
                    idp=CfnDomain.IdpProperty(
                        entity_id="entityId",
                        metadata_content="metadataContent"
                    ),
                    master_backend_role="masterBackendRole",
                    master_user_name="masterUserName",
                    roles_key="rolesKey",
                    session_timeout_minutes=123,
                    subject_key="subjectKey"
                )
            )

    def load_auth_mode(auth_mode: Optional[str]):
        if auth_mode is None:
            raise Exception("Authentication mode for Opensearch Dashboards needs to be set via AuthMode parameter")
        elif auth_mode.lower() == 'basic_auth':
            return AuthMode.BASIC_AUTH
        elif auth_mode.lower() == 'saml':
            return AuthMode.SAML
        else:
            raise Exception("Authentication mode must be basic_auth or saml")

    @property
    def config(self):
        return self._config

    @property
    def secret(self):
        return self._secret
