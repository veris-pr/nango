from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango.domain.models import Connection, IntegrationConfig
from nango.utils.crypto import decrypt_aes_gcm_base64


class PostgresIntegrationConfigRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_by_key(
        self,
        *,
        environment_id: int,
        provider_config_key: str,
    ) -> IntegrationConfig | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT *
                        FROM _nango_configs
                        WHERE unique_key = :provider_config_key
                          AND environment_id = :environment_id
                          AND deleted = false
                        LIMIT 1
                        """
                    ),
                    {
                        "environment_id": environment_id,
                        "provider_config_key": provider_config_key,
                    },
                )
            ).mappings().first()
        return None if row is None else _integration_from_row(cast(Mapping[str, object], row))

    async def list_for_environment(
        self,
        environment_id: int,
    ) -> tuple[IntegrationConfig, ...]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT *
                        FROM _nango_configs
                        WHERE environment_id = :environment_id
                          AND deleted = false
                        ORDER BY provider ASC, created_at ASC
                        """
                    ),
                    {"environment_id": environment_id},
                )
            ).mappings().all()
        return tuple(_integration_from_row(cast(Mapping[str, object], row)) for row in rows)


class PostgresConnectionRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        encryption_key: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._encryption_key = encryption_key

    async def get_by_id(
        self,
        *,
        environment_id: int,
        provider_config_key: str,
        connection_id: str,
    ) -> Connection | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT *
                        FROM _nango_connections
                        WHERE environment_id = :environment_id
                          AND provider_config_key = :provider_config_key
                          AND connection_id = :connection_id
                          AND deleted = false
                        LIMIT 1
                        """
                    ),
                    {
                        "environment_id": environment_id,
                        "provider_config_key": provider_config_key,
                        "connection_id": connection_id,
                    },
                )
            ).mappings().first()
        if row is None:
            return None
        return _connection_from_row(
            cast(Mapping[str, object], row),
            encryption_key=self._encryption_key,
        )

    async def list_for_environment(
        self,
        environment_id: int,
        *,
        connection_id: str | None = None,
        provider_config_keys: tuple[str, ...] = (),
        limit: int = 10_000,
        page: int = 0,
    ) -> tuple[Connection, ...]:
        where_provider_config_keys = ""
        if provider_config_keys:
            where_provider_config_keys = "AND provider_config_key = ANY(:provider_config_keys)"

        where_connection_id = ""
        if connection_id is not None:
            where_connection_id = "AND connection_id = :connection_id"

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        f"""
                        SELECT *
                        FROM _nango_connections
                        WHERE environment_id = :environment_id
                          AND deleted = false
                          {where_connection_id}
                          {where_provider_config_keys}
                        ORDER BY created_at DESC
                        LIMIT :limit
                        OFFSET :offset
                        """
                    ),
                    {
                        "environment_id": environment_id,
                        "connection_id": connection_id,
                        "provider_config_keys": list(provider_config_keys),
                        "limit": limit,
                        "offset": page * limit,
                    },
                )
            ).mappings().all()
        return tuple(
            _connection_from_row(
                cast(Mapping[str, object], row),
                encryption_key=self._encryption_key,
            )
            for row in rows
        )


def _integration_from_row(row: Mapping[str, object]) -> IntegrationConfig:
    return IntegrationConfig(
        id=_required_int(row, "id"),
        environmentId=_required_int(row, "environment_id"),
        providerConfigKey=_required_str(row, "unique_key"),
        provider=_required_str(row, "provider"),
        oauthClientId=_optional_str(row, "oauth_client_id"),
        oauthScopes=_scopes_tuple(row.get("oauth_scopes")),
        forwardWebhooks=_required_bool(row, "forward_webhooks"),
        missingFields=_string_tuple(row.get("missing_fields")),
        createdAt=_required_datetime(row, "created_at"),
        updatedAt=_required_datetime(row, "updated_at"),
    )


def _connection_from_row(
    row: Mapping[str, object],
    *,
    encryption_key: str | None,
) -> Connection:
    return Connection(
        id=_required_int(row, "id"),
        environmentId=_required_int(row, "environment_id"),
        configId=_required_int(row, "config_id"),
        providerConfigKey=_required_str(row, "provider_config_key"),
        connectionId=_required_str(row, "connection_id"),
        credentials=_connection_credentials(row, encryption_key=encryption_key),
        connectionConfig=_json_object(row.get("connection_config")),
        metadata=_optional_json_object(row.get("metadata")),
        tags=_string_dict(row.get("tags")),
        lastFetchedAt=_optional_datetime(row, "last_fetched_at"),
        createdAt=_required_datetime(row, "created_at"),
        updatedAt=_required_datetime(row, "updated_at"),
    )


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int):
        raise RuntimeError(f"Expected integer column: {key}")
    return value


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise RuntimeError(f"Expected string column: {key}")
    return value


def _optional_str(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"Expected string column: {key}")
    return value


def _required_bool(row: Mapping[str, object], key: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise RuntimeError(f"Expected boolean column: {key}")
    return value


def _required_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row.get(key)
    if not isinstance(value, datetime):
        raise RuntimeError(f"Expected datetime column: {key}")
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _optional_datetime(row: Mapping[str, object], key: str) -> datetime | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise RuntimeError(f"Expected datetime column: {key}")
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str))
    if isinstance(value, tuple):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _scopes_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(scope for scope in value.split(",") if scope)
    return _string_tuple(value)


def _connection_credentials(
    row: Mapping[str, object],
    *,
    encryption_key: str | None,
) -> dict[str, object]:
    credentials = _json_object(row.get("credentials"))
    encrypted = credentials.get("encrypted_credentials")
    iv = row.get("credentials_iv")
    auth_tag = row.get("credentials_tag")
    if not isinstance(encrypted, str) or not isinstance(iv, str) or not isinstance(auth_tag, str):
        return credentials
    if not encryption_key:
        return credentials

    decrypted = json.loads(decrypt_aes_gcm_base64(encryption_key, encrypted, iv, auth_tag))
    if not isinstance(decrypted, dict):
        raise RuntimeError("Expected decrypted connection credentials to be a JSON object")
    return {str(key): value for key, value in decrypted.items()}


def _json_object(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise RuntimeError("Expected JSON object column")
    return {str(key): cast(object, item) for key, item in value.items()}


def _optional_json_object(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    return _json_object(value)


def _string_dict(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise RuntimeError("Expected JSON object column")
    return {str(key): item for key, item in value.items() if isinstance(item, str)}
