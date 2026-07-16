"""SQLAlchemy implementation of :class:`PrivateKeyRepository`.

Mirrors ``packages/keystore/lib/models/privatekeys.ts``:
- ``createPrivateKey``: generate ``nango_${entityType}_${random_hex}``, PBKDF2
  hash, AES-GCM encrypt (stored as ``b\"{ct}:{iv}:{tag}\"``), insert.
- ``getPrivateKey``: hash token, lookup by hash + not expired, update
  ``last_access_at``.
- ``deletePrivateKey``: hash + entity_type, delete.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.keystore.domain.private_key import PrivateKey, PrivateKeyEntityType
from nango_py.shared.crypto import encrypt_aes_gcm, hash_secret

_KEY_RANDOM_BYTES = 32


class SqlAlchemyPrivateKeyRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        encryption_key: str,
    ) -> None:
        self._session_factory = session_factory
        self._encryption_key = encryption_key

    async def create_private_key(
        self,
        *,
        display_name: str,
        entity_type: PrivateKeyEntityType,
        entity_id: int,
        account_id: int,
        environment_id: int,
        ttl_ms: int | None = None,
    ) -> tuple[str, PrivateKey]:
        random = os.urandom(_KEY_RANDOM_BYTES).hex()
        key_value = f"nango_{entity_type}_{random}"
        key_hash = hash_secret(key_value, self._encryption_key)

        encrypted: bytes | None = None
        if self._encryption_key:
            ct, iv, tag = encrypt_aes_gcm(key_value, self._encryption_key)
            encrypted = f"{ct}:{iv}:{tag}".encode("ascii")

        now = datetime.now(UTC)
        expires_at = now + timedelta(milliseconds=ttl_ms) if ttl_ms else None

        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        INSERT INTO private_keys
                        (display_name, account_id, environment_id, encrypted, hash,
                         expires_at, entity_type, entity_id)
                        VALUES (:dn, :aid, :eid, :enc, :hash, :exp, :et, :eid_)
                        RETURNING *
                        """
                    ),
                    {
                        "dn": display_name,
                        "aid": account_id,
                        "eid": environment_id,
                        "enc": encrypted,
                        "hash": key_hash,
                        "exp": expires_at,
                        "et": entity_type,
                        "eid_": entity_id,
                    },
                )
            ).mappings().first()
            await session.commit()

        if row is None:
            raise RuntimeError("failed to create private key")
        return key_value, _private_key_from_row(cast(dict[str, Any], row))

    async def get_private_key(self, key_value: str) -> PrivateKey | None:
        key_hash = hash_secret(key_value, self._encryption_key)
        now = datetime.now(UTC)

        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        UPDATE private_keys SET last_access_at = :now
                        WHERE hash = :hash
                          AND (expires_at IS NULL OR expires_at > :now)
                        RETURNING *
                        """
                    ),
                    {"now": now, "hash": key_hash},
                )
            ).mappings().first()
            await session.commit()

        if row is None:
            return None
        return _private_key_from_row(cast(dict[str, Any], row))

    async def delete_private_key(
        self, *, key_value: str, entity_type: PrivateKeyEntityType
    ) -> bool:
        key_hash = hash_secret(key_value, self._encryption_key)

        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        DELETE FROM private_keys
                        WHERE hash = :hash AND entity_type = :et
                        RETURNING id
                        """
                    ),
                    {"hash": key_hash, "et": entity_type},
                )
            ).mappings().first()
            await session.commit()

        return row is not None


def _private_key_from_row(row: dict[str, Any]) -> PrivateKey:
    return PrivateKey(
        id=_required_int(row, "id"),
        display_name=_required_str(row, "display_name"),
        account_id=_required_int(row, "account_id"),
        environment_id=_required_int(row, "environment_id"),
        encrypted=row.get("encrypted"),
        hash=_required_str(row, "hash"),
        created_at=_required_datetime(row, "created_at"),
        expires_at=_optional_datetime(row, "expires_at"),
        last_access_at=_optional_datetime(row, "last_access_at"),
        entity_type=cast(PrivateKeyEntityType, _required_str(row, "entity_type")),
        entity_id=_required_int(row, "entity_id"),
    )


def _required_int(row: dict[str, Any], key: str) -> int:
    value = row[key]
    if not isinstance(value, int):
        raise RuntimeError(f"expected integer column: {key}")
    return value


def _required_str(row: dict[str, Any], key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise RuntimeError(f"expected string column: {key}")
    return value


def _required_datetime(row: dict[str, Any], key: str) -> Any:
    from datetime import datetime

    value = row[key]
    if not isinstance(value, datetime):
        raise RuntimeError(f"expected datetime column: {key}")
    return value


def _optional_datetime(row: dict[str, Any], key: str) -> Any:
    from datetime import datetime

    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise RuntimeError(f"expected datetime column: {key}")
    return value