from __future__ import annotations

from typing import Protocol

from nango.domain.errors import integration_already_exists
from nango.domain.models import Connection, IntegrationConfig, utc_now


class IntegrationConfigRepository(Protocol):
    def create(
        self,
        *,
        environment_id: int,
        provider_config_key: str,
        provider: str,
        oauth_client_id: str | None = None,
        oauth_scopes: tuple[str, ...] = (),
        forward_webhooks: bool = True,
        missing_fields: tuple[str, ...] = (),
    ) -> IntegrationConfig: ...

    def get_by_key(
        self,
        *,
        environment_id: int,
        provider_config_key: str,
    ) -> IntegrationConfig | None: ...

    def get_id_by_key(self, *, environment_id: int, provider_config_key: str) -> int | None: ...

    def list_for_environment(self, environment_id: int) -> tuple[IntegrationConfig, ...]: ...


class ConnectionRepository(Protocol):
    def upsert(
        self,
        *,
        environment_id: int,
        config_id: int,
        provider_config_key: str,
        connection_id: str,
        credentials: dict[str, object],
        connection_config: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
        tags: dict[str, str] | None = None,
        private_key_id: int | None = None,
    ) -> tuple[Connection, str]: ...

    def update_private_key_id(self, connection: Connection, private_key_id: int) -> Connection: ...

    def get_by_id(
        self,
        *,
        environment_id: int,
        provider_config_key: str,
        connection_id: str,
    ) -> Connection | None: ...

    def list_for_environment(
        self,
        environment_id: int,
        *,
        connection_id: str | None = None,
        provider_config_keys: tuple[str, ...] = (),
        search: str | None = None,
        end_user_id: str | None = None,
        end_user_organization_id: str | None = None,
        tags: dict[str, str] | None = None,
        limit: int = 10_000,
        page: int = 0,
    ) -> tuple[Connection, ...]: ...


class InMemoryIntegrationConfigRepository:
    def __init__(self) -> None:
        self._next_id = 1
        self._configs_by_key: dict[tuple[int, str], IntegrationConfig] = {}

    def create(
        self,
        *,
        environment_id: int,
        provider_config_key: str,
        provider: str,
        oauth_client_id: str | None = None,
        oauth_scopes: tuple[str, ...] = (),
        forward_webhooks: bool = True,
        missing_fields: tuple[str, ...] = (),
    ) -> IntegrationConfig:
        key = (environment_id, provider_config_key)
        if key in self._configs_by_key:
            raise integration_already_exists(provider_config_key)

        now = utc_now()
        config = IntegrationConfig(
            id=self._next_id,
            environmentId=environment_id,
            providerConfigKey=provider_config_key,
            provider=provider,
            oauthClientId=oauth_client_id,
            oauthScopes=oauth_scopes,
            forwardWebhooks=forward_webhooks,
            missingFields=missing_fields,
            createdAt=now,
            updatedAt=now,
        )
        self._next_id += 1
        self._configs_by_key[key] = config
        return config

    def get_by_key(
        self,
        *,
        environment_id: int,
        provider_config_key: str,
    ) -> IntegrationConfig | None:
        return self._configs_by_key.get((environment_id, provider_config_key))

    def get_id_by_key(self, *, environment_id: int, provider_config_key: str) -> int | None:
        config = self.get_by_key(
            environment_id=environment_id,
            provider_config_key=provider_config_key,
        )
        return None if config is None else config.id

    def list_for_environment(self, environment_id: int) -> tuple[IntegrationConfig, ...]:
        return tuple(
            config
            for (config_environment_id, _key), config in self._configs_by_key.items()
            if config_environment_id == environment_id
        )


class InMemoryConnectionRepository:
    def __init__(self) -> None:
        self._next_id = 1
        self._connections_by_key: dict[tuple[int, str, str], Connection] = {}

    def upsert(
        self,
        *,
        environment_id: int,
        config_id: int,
        provider_config_key: str,
        connection_id: str,
        credentials: dict[str, object],
        connection_config: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
        tags: dict[str, str] | None = None,
        private_key_id: int | None = None,
    ) -> tuple[Connection, str]:
        key = (environment_id, provider_config_key, connection_id)
        existing = self._connections_by_key.get(key)
        operation = "override" if existing else "creation"
        now = utc_now()
        resolved_connection_config = connection_config
        if resolved_connection_config is None and existing is not None:
            resolved_connection_config = existing.connection_config
        resolved_metadata = metadata
        if resolved_metadata is None and existing is not None:
            resolved_metadata = existing.metadata
        resolved_tags = tags if tags is not None else {}
        if tags is None and existing is not None:
            resolved_tags = existing.tags
        resolved_private_key_id = private_key_id
        if resolved_private_key_id is None and existing is not None:
            resolved_private_key_id = existing.private_key_id

        connection = Connection(
            id=existing.id if existing else self._next_id,
            environmentId=environment_id,
            configId=config_id,
            providerConfigKey=provider_config_key,
            connectionId=connection_id,
            credentials=dict(credentials),
            connectionConfig=dict(resolved_connection_config or {}),
            metadata=resolved_metadata,
            tags=dict(resolved_tags),
            privateKeyId=resolved_private_key_id,
            createdAt=existing.created_at if existing else now,
            updatedAt=now,
        )
        if existing is None:
            self._next_id += 1
        self._connections_by_key[key] = connection
        return connection, operation

    def update_private_key_id(self, connection: Connection, private_key_id: int) -> Connection:
        updated = connection.model_copy(
            update={"private_key_id": private_key_id, "updated_at": utc_now()}
        )
        key = (updated.environment_id, updated.provider_config_key, updated.connection_id)
        self._connections_by_key[key] = updated
        return updated

    def get_by_id(
        self,
        *,
        environment_id: int,
        provider_config_key: str,
        connection_id: str,
    ) -> Connection | None:
        return self._connections_by_key.get((environment_id, provider_config_key, connection_id))

    def list_for_environment(
        self,
        environment_id: int,
        *,
        connection_id: str | None = None,
        provider_config_keys: tuple[str, ...] = (),
        search: str | None = None,
        end_user_id: str | None = None,
        end_user_organization_id: str | None = None,
        tags: dict[str, str] | None = None,
        limit: int = 10_000,
        page: int = 0,
    ) -> tuple[Connection, ...]:
        connections = [
            connection
            for (
                connection_environment_id,
                _,
                stored_connection_id,
            ), connection in self._connections_by_key.items()
            if connection_environment_id == environment_id
            and (connection_id is None or stored_connection_id == connection_id)
            and (
                not provider_config_keys
                or connection.provider_config_key in provider_config_keys
            )
            and _matches_search(connection, search)
            and _matches_end_user_id(connection, end_user_id)
            and _matches_end_user_organization_id(connection, end_user_organization_id)
            and _matches_tags(connection, tags)
        ]
        connections.sort(key=lambda connection: connection.created_at, reverse=True)
        offset = page * limit
        return tuple(connections[offset : offset + limit])


def _matches_search(connection: Connection, search: str | None) -> bool:
    if not search:
        return True
    search_lower = search.lower()
    if search_lower in connection.connection_id.lower():
        return True
    end_user = connection.end_user or {}
    display_name = end_user.get("display_name")
    email = end_user.get("email")
    return (
        isinstance(display_name, str)
        and search_lower in display_name.lower()
    ) or (
        isinstance(email, str)
        and search_lower in email.lower()
    )


def _matches_end_user_id(connection: Connection, end_user_id: str | None) -> bool:
    if end_user_id is None:
        return True
    return connection.end_user is not None and connection.end_user.get("end_user_id") == end_user_id


def _matches_end_user_organization_id(
    connection: Connection,
    end_user_organization_id: str | None,
) -> bool:
    if end_user_organization_id is None:
        return True
    return (
        connection.end_user is not None
        and connection.end_user.get("organization_id") == end_user_organization_id
    )


def _matches_tags(connection: Connection, tags: dict[str, str] | None) -> bool:
    if not tags:
        return True
    return all(connection.tags.get(key) == value for key, value in tags.items())
