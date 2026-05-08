from __future__ import annotations

from typing import Literal, cast

from nango.adapters.providers import Provider, ProviderCatalog, get_provider
from nango.domain.errors import integration_not_found, provider_not_found
from nango.domain.models import (
    Connection,
    ConnectionPrivateKey,
    ConnectionUpsertResult,
    DeployMetadata,
    IntegrationConfig,
)
from nango.domain.repositories import (
    InMemoryConnectionRepository,
    InMemoryIntegrationConfigRepository,
)
from nango.keystore import InMemoryPrivateKeyRepository, PrivateKeyEntityType
from nango.nango_yaml import ParsedNangoYaml


class ProviderResolver:
    def __init__(self, providers: ProviderCatalog | None = None) -> None:
        self._providers = providers

    def resolve(self, provider_name: str) -> Provider:
        if self._providers is not None:
            provider = self._providers.get(provider_name)
        else:
            provider = get_provider(provider_name)
        if provider is None:
            raise provider_not_found(provider_name)
        return provider


class IntegrationConfigService:
    def __init__(
        self,
        repository: InMemoryIntegrationConfigRepository | None = None,
        provider_resolver: ProviderResolver | None = None,
    ) -> None:
        self.repository = repository or InMemoryIntegrationConfigRepository()
        self.provider_resolver = provider_resolver or ProviderResolver()

    def create_integration(
        self,
        *,
        environment_id: int,
        provider_config_key: str,
        provider_name: str,
        oauth_client_id: str | None = None,
        oauth_scopes: tuple[str, ...] = (),
        forward_webhooks: bool = True,
    ) -> IntegrationConfig:
        provider = self.provider_resolver.resolve(provider_name)
        resolved_scopes = oauth_scopes or _provider_default_scopes(provider)
        missing_fields = _missing_integration_fields(provider, oauth_client_id)
        return self.repository.create(
            environment_id=environment_id,
            provider_config_key=provider_config_key,
            provider=provider_name,
            oauth_client_id=oauth_client_id,
            oauth_scopes=resolved_scopes,
            forward_webhooks=forward_webhooks,
            missing_fields=missing_fields,
        )

    def get_integration(
        self,
        *,
        environment_id: int,
        provider_config_key: str,
    ) -> IntegrationConfig | None:
        return self.repository.get_by_key(
            environment_id=environment_id,
            provider_config_key=provider_config_key,
        )


class ConnectionService:
    def __init__(
        self,
        *,
        integration_repository: InMemoryIntegrationConfigRepository,
        connection_repository: InMemoryConnectionRepository | None = None,
        private_key_repository: InMemoryPrivateKeyRepository | None = None,
    ) -> None:
        self.integration_repository = integration_repository
        self.connection_repository = connection_repository or InMemoryConnectionRepository()
        self.private_key_repository = private_key_repository

    def upsert_connection(
        self,
        *,
        environment_id: int,
        provider_config_key: str,
        connection_id: str,
        credentials: dict[str, object],
        connection_config: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
        tags: dict[str, str] | None = None,
        account_id: int | None = None,
        create_private_key: bool = False,
    ) -> ConnectionUpsertResult:
        integration = self.integration_repository.get_by_key(
            environment_id=environment_id,
            provider_config_key=provider_config_key,
        )
        if integration is None:
            raise integration_not_found(provider_config_key)

        connection, operation = self.connection_repository.upsert(
            environment_id=environment_id,
            config_id=integration.id,
            provider_config_key=provider_config_key,
            connection_id=connection_id,
            credentials=credentials,
            connection_config=connection_config,
            metadata=metadata,
            tags=tags,
        )
        private_key = None
        if create_private_key:
            private_key = self._create_private_key(connection, account_id)
            connection = self.connection_repository.update_private_key_id(
                connection,
                private_key.key_id,
            )

        operation_value = cast(Literal["creation", "override"], operation)
        return ConnectionUpsertResult(
            connection=connection,
            operation=operation_value,
            privateKey=private_key,
        )

    def _create_private_key(
        self,
        connection: Connection,
        account_id: int | None,
    ) -> ConnectionPrivateKey:
        if self.private_key_repository is None:
            raise RuntimeError("Private key repository is required to create connection keys")
        if account_id is None:
            raise RuntimeError("Account id is required to create connection keys")

        key_value, private_key = self.private_key_repository.create(
            display_name=f"Connection {connection.connection_id}",
            entity_type=PrivateKeyEntityType.CONNECTION,
            entity_id=connection.id,
            account_id=account_id,
            environment_id=connection.environment_id,
        )
        return ConnectionPrivateKey(
            keyValue=key_value,
            keyId=private_key.id,
            keyHash=private_key.hash,
        )


class DeployMetadataService:
    def from_parsed_nango_yaml(self, parsed: ParsedNangoYaml) -> DeployMetadata:
        return DeployMetadata.from_parsed_nango_yaml(parsed)


def _provider_default_scopes(provider: Provider) -> tuple[str, ...]:
    default_scopes = provider.get("default_scopes")
    if not isinstance(default_scopes, list):
        return ()
    return tuple(scope for scope in default_scopes if isinstance(scope, str))


def _missing_integration_fields(
    provider: Provider,
    oauth_client_id: str | None,
) -> tuple[str, ...]:
    auth_mode = provider.get("auth_mode")
    if auth_mode == "OAUTH2" and not oauth_client_id:
        return ("oauth_client_id",)
    return ()
