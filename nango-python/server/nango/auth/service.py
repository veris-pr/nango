from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from os import environ
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango.auth.models import (
    AccountContext,
    AccountSummary,
    AuthSource,
    EnvironmentSummary,
    SecretSummary,
)
from nango.keystore.crypto import hash_private_key_value
from nango.server.settings import Settings
from nango.utils.crypto import decrypt_aes_gcm_base64

ENV_SECRET_PREFIX = "NANGO_SECRET_KEY_"


class AuthService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        settings: Settings | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings or Settings.from_env()
        self._env = environ if env is None else env

    async def get_account_context_by_api_key(
        self,
        *,
        secret_key: str | None = None,
        internal_secret_key: str | None = None,
    ) -> AccountContext | None:
        key = secret_key or internal_secret_key
        if not key:
            return None

        env_context = await self._get_env_var_context(key)
        if env_context is not None:
            return env_context

        if self._session_factory is None:
            return None

        if secret_key is not None:
            return await self._get_customer_key_context(secret_key)
        return await self._get_internal_secret_context(internal_secret_key=key)

    async def _get_env_var_context(self, secret_key: str) -> AccountContext | None:
        for name, value in self._env.items():
            if not name.startswith(ENV_SECRET_PREFIX) or value != secret_key:
                continue

            if self._session_factory is None:
                return None

            environment_name = name.removeprefix(ENV_SECRET_PREFIX).lower()
            async with self._session_factory() as session:
                result = await session.execute(
                    text(
                        """
                        SELECT e.account_id
                        FROM _nango_environments AS e
                        WHERE e.name = :environment_name AND e.deleted = false
                        LIMIT 1
                        """
                    ),
                    {"environment_name": environment_name},
                )
                account_id = result.scalar_one_or_none()
            if account_id is None:
                return None
            return await self._get_context_by_account_and_env_name(
                account_id=account_id,
                environment_name=environment_name,
            )
        return None

    async def _get_context_by_account_and_env_name(
        self,
        *,
        account_id: int,
        environment_name: str,
    ) -> AccountContext | None:
        if self._session_factory is None:
            return None

        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT
                            a.id AS account_id,
                            a.uuid AS account_uuid,
                            a.created_at AS account_created_at,
                            a.updated_at AS account_updated_at,
                            e.id AS environment_id,
                            e.uuid AS environment_uuid,
                            e.name AS environment_name,
                            e.account_id AS environment_account_id,
                            e.public_key AS environment_public_key,
                            e.is_production AS environment_is_production,
                            e.created_at AS environment_created_at,
                            e.updated_at AS environment_updated_at,
                            e.deleted_at AS environment_deleted_at,
                            ds.id AS secret_id,
                            ds.environment_id AS secret_environment_id,
                            ds.display_name AS secret_display_name,
                            ds.secret AS secret_value,
                            ds.iv AS secret_iv,
                            ds.tag AS secret_tag,
                            ds.hashed AS secret_hashed,
                            ds.is_default AS secret_is_default,
                            ds.created_at AS secret_created_at,
                            ds.updated_at AS secret_updated_at,
                            ps.secret AS pending_secret_value,
                            ps.iv AS pending_secret_iv,
                            ps.tag AS pending_secret_tag
                        FROM _nango_environments AS e
                        JOIN _nango_accounts AS a ON a.id = e.account_id
                        JOIN api_secrets AS ds ON ds.environment_id = e.id AND ds.is_default = true
                        LEFT JOIN api_secrets AS ps
                            ON ps.environment_id = e.id AND ps.is_default = false
                        WHERE e.account_id = :account_id
                          AND e.name = :environment_name
                          AND e.deleted = false
                        LIMIT 1
                        """
                    ),
                    {"account_id": account_id, "environment_name": environment_name},
                )
            ).mappings().first()
        if row is None:
            return None
        return _context_from_row(cast(Mapping[str, object], row), auth_source="env_var")

    async def _get_customer_key_context(self, secret_key: str) -> AccountContext | None:
        if self._session_factory is None:
            return None

        secret_hash = hash_private_key_value(secret_key, self._settings.encryption_key)
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        WITH matched_customer_key AS (
                            SELECT ck.id, ckr.entity_id AS environment_id, ck.scopes
                            FROM customer_keys AS ck
                            JOIN customer_keys_relations AS ckr ON ckr.customer_key_id = ck.id
                            WHERE ck.hashed = :secret_hash
                              AND ck.key_type = 'api'
                              AND ck.deleted_at IS NULL
                              AND ckr.entity_type = 'environment'
                            LIMIT 1
                        ),
                        updated_customer_key AS (
                            UPDATE customer_keys AS ck
                            SET last_used_at = NOW()
                            FROM matched_customer_key AS mck
                            WHERE ck.id = mck.id
                              AND (
                                    ck.last_used_at IS NULL
                                 OR ck.last_used_at < NOW() - INTERVAL '1 minute'
                              )
                            RETURNING ck.id
                        )
                        SELECT
                            a.id AS account_id,
                            a.uuid AS account_uuid,
                            a.created_at AS account_created_at,
                            a.updated_at AS account_updated_at,
                            e.id AS environment_id,
                            e.uuid AS environment_uuid,
                            e.name AS environment_name,
                            e.account_id AS environment_account_id,
                            e.public_key AS environment_public_key,
                            e.is_production AS environment_is_production,
                            e.created_at AS environment_created_at,
                            e.updated_at AS environment_updated_at,
                            e.deleted_at AS environment_deleted_at,
                            ds.id AS secret_id,
                            ds.environment_id AS secret_environment_id,
                            ds.display_name AS secret_display_name,
                            ds.secret AS secret_value,
                            ds.iv AS secret_iv,
                            ds.tag AS secret_tag,
                            ds.hashed AS secret_hashed,
                            ds.is_default AS secret_is_default,
                            ds.created_at AS secret_created_at,
                            ds.updated_at AS secret_updated_at,
                            ps.secret AS pending_secret_value,
                            ps.iv AS pending_secret_iv,
                            ps.tag AS pending_secret_tag,
                            mck.scopes AS auth_scopes,
                            mck.id AS auth_api_key_id
                        FROM matched_customer_key AS mck
                        JOIN _nango_environments AS e ON e.id = mck.environment_id
                        JOIN _nango_accounts AS a ON a.id = e.account_id
                        JOIN api_secrets AS ds ON ds.environment_id = e.id AND ds.is_default = true
                        LEFT JOIN api_secrets AS ps
                            ON ps.environment_id = e.id AND ps.is_default = false
                        WHERE e.deleted = false
                        LIMIT 1
                        """
                    ),
                    {"secret_hash": secret_hash},
                )
            ).mappings().first()
        if row is None:
            return None
        return _context_from_row(cast(Mapping[str, object], row), auth_source="customer_key")

    async def _get_internal_secret_context(
        self,
        *,
        internal_secret_key: str,
    ) -> AccountContext | None:
        if self._session_factory is None:
            return None

        secret_hash = hash_private_key_value(internal_secret_key, self._settings.encryption_key)
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT
                            a.id AS account_id,
                            a.uuid AS account_uuid,
                            a.created_at AS account_created_at,
                            a.updated_at AS account_updated_at,
                            e.id AS environment_id,
                            e.uuid AS environment_uuid,
                            e.name AS environment_name,
                            e.account_id AS environment_account_id,
                            e.public_key AS environment_public_key,
                            e.is_production AS environment_is_production,
                            e.created_at AS environment_created_at,
                            e.updated_at AS environment_updated_at,
                            e.deleted_at AS environment_deleted_at,
                            ds.id AS secret_id,
                            ds.environment_id AS secret_environment_id,
                            ds.display_name AS secret_display_name,
                            ds.secret AS secret_value,
                            ds.iv AS secret_iv,
                            ds.tag AS secret_tag,
                            ds.hashed AS secret_hashed,
                            ds.is_default AS secret_is_default,
                            ds.created_at AS secret_created_at,
                            ds.updated_at AS secret_updated_at,
                            ps.secret AS pending_secret_value,
                            ps.iv AS pending_secret_iv,
                            ps.tag AS pending_secret_tag
                        FROM api_secrets AS auth_secret
                        JOIN _nango_environments AS e ON e.id = auth_secret.environment_id
                        JOIN _nango_accounts AS a ON a.id = e.account_id
                        JOIN api_secrets AS ds ON ds.environment_id = e.id AND ds.is_default = true
                        LEFT JOIN api_secrets AS ps
                            ON ps.environment_id = e.id AND ps.is_default = false
                        WHERE auth_secret.hashed = :secret_hash
                          AND auth_secret.is_default = true
                          AND e.deleted = false
                        LIMIT 1
                        """
                    ),
                    {"secret_hash": secret_hash},
                )
            ).mappings().first()
        if row is None:
            return None
        return _context_from_row(cast(Mapping[str, object], row), auth_source="api_secret")


def _context_from_row(
    row: Mapping[str, object],
    *,
    auth_source: AuthSource,
) -> AccountContext:
    default_secret = _decrypt_secret(
        secret=_required_str(row, "secret_value"),
        iv=_optional_str(row, "secret_iv"),
        tag=_optional_str(row, "secret_tag"),
    )
    pending_secret = _decrypt_secret(
        secret=_optional_str(row, "pending_secret_value"),
        iv=_optional_str(row, "pending_secret_iv"),
        tag=_optional_str(row, "pending_secret_tag"),
    )

    return AccountContext(
        account=AccountSummary(
            id=_required_int(row, "account_id"),
            uuid=_optional_str(row, "account_uuid"),
            createdAt=_required_datetime(row, "account_created_at"),
            updatedAt=_required_datetime(row, "account_updated_at"),
        ),
        environment=EnvironmentSummary(
            id=_required_int(row, "environment_id"),
            uuid=_optional_str(row, "environment_uuid"),
            name=_required_str(row, "environment_name"),
            accountId=_required_int(row, "environment_account_id"),
            publicKey=_optional_str(row, "environment_public_key"),
            secretKey=default_secret or "",
            pendingSecretKey=pending_secret,
            isProduction=_required_bool(row, "environment_is_production"),
            createdAt=_required_datetime(row, "environment_created_at"),
            updatedAt=_required_datetime(row, "environment_updated_at"),
            deletedAt=_optional_datetime(row, "environment_deleted_at"),
        ),
        secret=SecretSummary(
            id=_required_int(row, "secret_id"),
            environmentId=_required_int(row, "secret_environment_id"),
            displayName=_required_str(row, "secret_display_name"),
            secret=default_secret or "",
            hashed=_required_str(row, "secret_hashed"),
            isDefault=_required_bool(row, "secret_is_default"),
            createdAt=_required_datetime(row, "secret_created_at"),
            updatedAt=_required_datetime(row, "secret_updated_at"),
        ),
        authSource=auth_source,
        scopes=tuple(_string_tuple(row.get("auth_scopes"))),
        apiKeyId=_optional_int(row, "auth_api_key_id"),
    )


def _decrypt_secret(secret: str | None, iv: str | None, tag: str | None) -> str | None:
    if secret is None:
        return None
    if not iv or not tag:
        return secret
    settings = Settings.from_env()
    if not settings.encryption_key:
        return secret

    return decrypt_aes_gcm_base64(settings.encryption_key, secret, iv, tag)


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int):
        raise RuntimeError(f"Expected integer column: {key}")
    return value


def _optional_int(row: Mapping[str, object], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
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
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    raise RuntimeError(f"Expected datetime column: {key}")


def _optional_datetime(row: Mapping[str, object], key: str) -> datetime | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    raise RuntimeError(f"Expected datetime column: {key}")


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str))
    if isinstance(value, tuple):
        return tuple(item for item in value if isinstance(item, str))
    return ()
