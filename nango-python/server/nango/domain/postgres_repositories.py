from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango.domain.models import IntegrationConfig


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
