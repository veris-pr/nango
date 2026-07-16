"""SQLAlchemy implementation of :class:`AuthGateway`.

Reads the authoritative schemas produced by the Knex migrations:
``api_secrets``, ``customer_keys``, ``customer_keys_relations``,
``_nango_environments``, ``_nango_accounts``.

Mirrors ``packages/shared/lib/services/account.service.ts``:
- ``resolve_by_secret_key``  → ``getAccountContextByCustomerKey``
- ``resolve_by_internal_secret_key`` → ``getAccountContextByInternalSecret``

UUID columns are cast to ``::text`` in SQL so asyncpg returns plain strings
matching the domain model. Scopes (``text[]``) are returned as a tuple.

Deferred from this slice (tracked in the plan, not required for the read
response):
- ``last_used_at`` debounced update on customer-key lookup (observability side effect)
- ``pending_secret_key`` resolution (secret rotation)
- ``plans`` join (billing)
- env-var secret key path (``NANGO_SECRET_KEY_*``) — added when the persist/internal routes land
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.auth.domain.context import (
    Account,
    ApiSecret,
    AuthenticatedContext,
    Environment,
    Scopes,
)
from nango_py.shared.crypto import decrypt_api_secret, hash_secret

_WILDCARD_SCOPES: tuple[str, ...] = ("environment:*",)

_CUSTOMER_KEY_QUERY = text(
    """
    WITH matched_customer_key AS (
        SELECT ck.id, ckr.entity_id AS environment_id, ck.scopes
        FROM customer_keys ck
        JOIN customer_keys_relations ckr ON ckr.customer_key_id = ck.id
        WHERE ck.hashed = :hash
          AND ck.key_type = 'api'
          AND ck.deleted_at IS NULL
          AND ckr.entity_type = 'environment'
        LIMIT 1
    )
    SELECT
        a.id            AS account_id,
        a.name          AS account_name,
        a.uuid::text    AS account_uuid,
        a.created_at    AS account_created_at,
        a.updated_at    AS account_updated_at,
        e.id            AS environment_id,
        e.name          AS environment_name,
        e.account_id    AS environment_account_id,
        e.uuid::text    AS environment_uuid,
        e.public_key::text AS environment_public_key,
        e.is_production AS environment_is_production,
        e.created_at    AS environment_created_at,
        e.updated_at    AS environment_updated_at,
        ds.id           AS secret_id,
        ds.environment_id AS secret_environment_id,
        ds.display_name AS secret_display_name,
        ds.secret       AS secret_value,
        ds.iv           AS secret_iv,
        ds.tag          AS secret_tag,
        ds.hashed       AS secret_hashed,
        ds.is_default   AS secret_is_default,
        mck.scopes      AS auth_scopes,
        mck.id          AS auth_api_key_id
    FROM matched_customer_key mck
    JOIN _nango_environments e ON e.id = mck.environment_id
    JOIN _nango_accounts a ON a.id = e.account_id
    JOIN api_secrets ds ON ds.environment_id = e.id AND ds.is_default = true
    WHERE e.deleted = false
    LIMIT 1
    """
)

_INTERNAL_SECRET_QUERY = text(
    """
    SELECT
        a.id            AS account_id,
        a.name          AS account_name,
        a.uuid::text    AS account_uuid,
        a.created_at    AS account_created_at,
        a.updated_at    AS account_updated_at,
        e.id            AS environment_id,
        e.name          AS environment_name,
        e.account_id    AS environment_account_id,
        e.uuid::text    AS environment_uuid,
        e.public_key::text AS environment_public_key,
        e.is_production AS environment_is_production,
        e.created_at    AS environment_created_at,
        e.updated_at    AS environment_updated_at,
        ds.id           AS secret_id,
        ds.environment_id AS secret_environment_id,
        ds.display_name AS secret_display_name,
        ds.secret       AS secret_value,
        ds.iv           AS secret_iv,
        ds.tag          AS secret_tag,
        ds.hashed       AS secret_hashed,
        ds.is_default   AS secret_is_default
    FROM api_secrets auth_secret
    JOIN _nango_environments e ON e.id = auth_secret.environment_id
    JOIN _nango_accounts a ON a.id = e.account_id
    JOIN api_secrets ds ON ds.environment_id = e.id AND ds.is_default = true
    WHERE auth_secret.hashed = :hash
      AND auth_secret.is_default = true
      AND e.deleted = false
    LIMIT 1
    """
)


class SqlAlchemyAuthGateway:
    """Production :class:`AuthGateway` over the migrated app DB.

    Fail-closed: an unknown or malformed key resolves to ``None``; the caller
    maps that to ``UnknownAccount``. Missing config (no encryption key) is
    accepted only because the TS ``shouldEncrypt()`` path is pass-through.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        encryption_key: str,
    ) -> None:
        self._session_factory = session_factory
        self._encryption_key = encryption_key

    async def resolve_by_secret_key(self, secret_key: str) -> AuthenticatedContext | None:
        hashed = hash_secret(secret_key, self._encryption_key)
        async with self._session_factory() as session:
            row = (
                await session.execute(_CUSTOMER_KEY_QUERY, {"hash": hashed})
            ).mappings().first()
        if row is None:
            return None
        return self._context_from_row(
            cast(dict[str, Any], row), auth_source="customer_key"
        )

    async def resolve_by_internal_secret_key(
        self, internal_secret_key: str
    ) -> AuthenticatedContext | None:
        hashed = hash_secret(internal_secret_key, self._encryption_key)
        async with self._session_factory() as session:
            row = (
                await session.execute(_INTERNAL_SECRET_QUERY, {"hash": hashed})
            ).mappings().first()
        if row is None:
            return None
        return self._context_from_row(
            cast(dict[str, Any], row), auth_source="api_secret"
        )

    async def resolve_by_public_key(
        self, public_key: str
    ) -> AuthenticatedContext | None:
        """Resolve an environment by its public key (UUID v4).

        Mirrors ``getAccountContextByPublicKey`` — looks up
        ``_nango_environments.public_key`` and returns the full context.
        Public key auth is deprecated but still supported.
        """
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT
                            a.id            AS account_id,
                            a.name          AS account_name,
                            a.uuid::text    AS account_uuid,
                            a.created_at    AS account_created_at,
                            a.updated_at    AS account_updated_at,
                            e.id            AS environment_id,
                            e.name          AS environment_name,
                            e.account_id    AS environment_account_id,
                            e.uuid::text    AS environment_uuid,
                            e.public_key::text AS environment_public_key,
                            e.is_production AS environment_is_production,
                            e.created_at    AS environment_created_at,
                            e.updated_at    AS environment_updated_at,
                            ds.id           AS secret_id,
                            ds.environment_id AS secret_environment_id,
                            ds.display_name AS secret_display_name,
                            ds.secret       AS secret_value,
                            ds.iv           AS secret_iv,
                            ds.tag          AS secret_tag,
                            ds.hashed       AS secret_hashed,
                            ds.is_default   AS secret_is_default
                        FROM _nango_environments AS e
                        JOIN _nango_accounts AS a ON a.id = e.account_id
                        JOIN api_secrets AS ds ON ds.environment_id = e.id AND ds.is_default = true
                        WHERE e.public_key::text = :public_key
                          AND e.deleted = false
                        LIMIT 1
                        """
                    ),
                    {"public_key": public_key},
                )
            ).mappings().first()
        if row is None:
            return None
        return self._context_from_row(
            cast(dict[str, Any], row), auth_source="env_var"
        )

    async def resolve_by_connect_session_token(
        self, token: str
    ) -> AuthenticatedContext | None:
        """Resolve a connect session token to a minimal auth context.

        Looks up ``connect_sessions`` by token, joins to environment + account,
        and returns an AuthenticatedContext with wildcard scopes.
        """
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT
                            a.id            AS account_id,
                            a.name          AS account_name,
                            a.uuid::text    AS account_uuid,
                            e.id            AS environment_id,
                            e.name          AS environment_name,
                            e.account_id    AS environment_account_id,
                            e.uuid::text    AS environment_uuid,
                            e.is_production AS environment_is_production,
                            ds.id           AS secret_id,
                            ds.environment_id AS secret_environment_id,
                            ds.display_name AS secret_display_name,
                            ds.secret       AS secret_value,
                            ds.iv           AS secret_iv,
                            ds.tag          AS secret_tag,
                            ds.hashed       AS secret_hashed,
                            ds.is_default   AS secret_is_default
                        FROM connect_sessions AS cs
                        JOIN _nango_environments AS e ON e.id = cs.environment_id
                        JOIN _nango_accounts AS a ON a.id = e.account_id
                        JOIN api_secrets AS ds ON ds.environment_id = e.id AND ds.is_default = true
                        WHERE cs.token = :token
                          AND cs.deleted_at IS NULL
                          AND cs.expires_at > NOW()
                        LIMIT 1
                        """
                    ),
                    {"token": token},
                )
            ).mappings().first()
        if row is None:
            return None
        return self._context_from_row(
            cast(dict[str, Any], row), auth_source="connect_session"
        )

    def _context_from_row(
        self,
        row: dict[str, Any],
        *,
        auth_source: str,
    ) -> AuthenticatedContext:
        account = Account(
            id=_required_int(row, "account_id"),
            name=_required_str(row, "account_name"),
            uuid=_optional_str(row, "account_uuid"),
        )
        environment = Environment(
            id=_required_int(row, "environment_id"),
            name=_required_str(row, "environment_name"),
            account_id=_required_int(row, "environment_account_id"),
            uuid=_required_str(row, "environment_uuid"),
            is_production=_required_bool(row, "environment_is_production"),
        )
        decrypted_secret = decrypt_api_secret(
            _required_str(row, "secret_value"),
            _optional_str(row, "secret_iv"),
            _optional_str(row, "secret_tag"),
            self._encryption_key,
        )
        secret = ApiSecret(
            id=_required_int(row, "secret_id"),
            environment_id=_required_int(row, "secret_environment_id"),
            display_name=_required_str(row, "secret_display_name"),
            secret=decrypted_secret,
            hashed=_required_str(row, "secret_hashed"),
            is_default=_required_bool(row, "secret_is_default"),
        )
        if auth_source == "customer_key":
            scopes = _scopes_tuple(row.get("auth_scopes"))
            api_key_id = _optional_int(row, "auth_api_key_id")
        else:
            scopes = _WILDCARD_SCOPES
            api_key_id = None
        return AuthenticatedContext(
            account=account,
            environment=environment,
            secret=secret,
            auth_source=auth_source,  # type: ignore[arg-type]
            scopes=Scopes(scopes),
            api_key_id=api_key_id,
        )


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


def _required_bool(row: dict[str, Any], key: str) -> bool:
    value = row[key]
    if not isinstance(value, bool):
        raise RuntimeError(f"expected boolean column: {key}")
    return value


def _scopes_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(item for item in value if isinstance(item, str))
    return ()