"""SQLAlchemy implementation of :class:`IntegrationRepository`.

Reads ``_nango_configs`` and decrypts ``oauth_client_secret`` and ``custom``
the same way ``packages/shared/lib/utils/encryption.manager.ts``
``decryptProviderConfig`` does. Shared-credential rows are not joined here:
the public read response returns empty ``client_id``/``client_secret`` whenever
``shared_credentials_id`` is set, so only the flag is needed.

The list path selects only the public fields (no secret/custom decryption),
mirroring ``listProviderConfigs`` consumed by ``integrationToPublicApi``
which never touches credentials.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.integrations.domain.integration import Integration
from nango_py.shared.crypto import decrypt_aes_gcm

_QUERY = text(
    """
    SELECT
        id,
        unique_key,
        provider,
        environment_id,
        created_at,
        updated_at,
        oauth_client_id,
        oauth_client_secret,
        oauth_client_secret_iv,
        oauth_client_secret_tag,
        oauth_scopes,
        app_link,
        custom,
        display_name,
        forward_webhooks,
        shared_credentials_id
    FROM _nango_configs
    WHERE unique_key = :unique_key
      AND environment_id = :environment_id
      AND deleted = false
    LIMIT 1
    """
)

_LIST_QUERY = text(
    """
    SELECT
        id,
        unique_key,
        provider,
        environment_id,
        created_at,
        updated_at,
        display_name,
        forward_webhooks,
        shared_credentials_id
    FROM _nango_configs
    WHERE environment_id = :environment_id
      AND deleted = false
    ORDER BY provider ASC, created_at ASC
    """
)


class SqlAlchemyIntegrationRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        encryption_key: str,
    ) -> None:
        self._session_factory = session_factory
        self._encryption_key = encryption_key

    async def get_by_unique_key(
        self,
        *,
        environment_id: int,
        unique_key: str,
    ) -> Integration | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    _QUERY,
                    {"unique_key": unique_key, "environment_id": environment_id},
                )
            ).mappings().first()
        if row is None:
            return None
        return self._integration_from_row(cast(dict[str, Any], row))

    async def list_for_environment(self, *, environment_id: int) -> list[Integration]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(_LIST_QUERY, {"environment_id": environment_id})
            ).mappings().all()
        return [self._summary_from_row(cast(dict[str, Any], row)) for row in rows]

    def _summary_from_row(self, row: dict[str, Any]) -> Integration:
        """Lightweight mapping for list responses — no secret/custom decryption."""
        return Integration(
            id=_required_int(row, "id"),
            unique_key=_required_str(row, "unique_key"),
            provider=_required_str(row, "provider"),
            environment_id=_required_int(row, "environment_id"),
            created_at=_required_datetime(row, "created_at"),
            updated_at=_required_datetime(row, "updated_at"),
            display_name=_optional_str(row, "display_name"),
            forward_webhooks=_forward_webhooks(row.get("forward_webhooks")),
            shared_credentials_id=_optional_int(row, "shared_credentials_id"),
        )

    def _integration_from_row(self, row: dict[str, Any]) -> Integration:
        return Integration(
            id=_required_int(row, "id"),
            unique_key=_required_str(row, "unique_key"),
            provider=_required_str(row, "provider"),
            environment_id=_required_int(row, "environment_id"),
            created_at=_required_datetime(row, "created_at"),
            updated_at=_required_datetime(row, "updated_at"),
            oauth_client_id=_optional_str(row, "oauth_client_id"),
            oauth_client_secret=_decrypted_secret(row, self._encryption_key),
            oauth_scopes=_optional_str(row, "oauth_scopes"),
            app_link=_optional_str(row, "app_link"),
            custom=_decrypted_custom(row.get("custom"), self._encryption_key),
            display_name=_optional_str(row, "display_name"),
            forward_webhooks=_forward_webhooks(row.get("forward_webhooks")),
            shared_credentials_id=_optional_int(row, "shared_credentials_id"),
        )


def _decrypted_secret(row: dict[str, Any], encryption_key: str) -> str | None:
    secret = _optional_str(row, "oauth_client_secret")
    if secret is None:
        return None
    iv = _optional_str(row, "oauth_client_secret_iv")
    tag = _optional_str(row, "oauth_client_secret_tag")
    if not encryption_key or not iv or not tag:
        return secret
    return decrypt_aes_gcm(secret, iv, tag, encryption_key)


def _decrypted_custom(value: Any, encryption_key: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        return {}
    if (
        encryption_key
        and "encryptedValue" in value
        and "iv" in value
        and "authTag" in value
    ):
        decrypted = decrypt_aes_gcm(
            _required_str(value, "encryptedValue"),
            _required_str(value, "iv"),
            _required_str(value, "authTag"),
            encryption_key,
        )
        parsed = json.loads(decrypted)
        if not isinstance(parsed, dict):
            return {}
        return cast("dict[str, object]", parsed)
    return cast("dict[str, object]", value)


def _forward_webhooks(value: Any) -> bool:
    return bool(value) if value is not None else True


def _required_int(row: dict[str, Any], key: str) -> int:
    value = row[key]
    if not isinstance(value, int):
        raise RuntimeError(f"expected integer column: {key}")
    return value


def _optional_int(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise RuntimeError(f"expected integer column: {key}")
    return value


def _required_str(row: dict[str, Any], key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise RuntimeError(f"expected string column: {key}")
    return value


def _optional_str(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"expected string column: {key}")
    return value


def _required_datetime(row: dict[str, Any], key: str) -> datetime:
    value = row[key]
    if not isinstance(value, datetime):
        raise RuntimeError(f"expected datetime column: {key}")
    return value