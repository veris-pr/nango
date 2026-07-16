"""SQLAlchemy implementation of :class:`ConnectionRepository`.

Reads ``_nango_connections`` joined with ``end_users``, ``_nango_active_logs``
(aggregated) and ``_nango_configs`` (provider), mirroring
``packages/shared/lib/services/connection.service.ts`` ``listConnections`` and
``getConnection``.

The list path never decrypts credentials (list items omit them); the single
path decrypts ``credentials`` via ``decryptConnection`` semantics
(``credentials.encrypted_credentials`` + ``credentials_iv`` + ``credentials_tag``
→ AES-GCM decrypt + JSON parse, else use stored credentials).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.connections.application.gateway import ListConnectionsFilters
from nango_py.connections.domain.connection import (
    Connection,
    ConnectionActiveLog,
    ConnectionEndUser,
    ConnectionEndUserOrganization,
)
from nango_py.shared.crypto import decrypt_aes_gcm, encrypt_aes_gcm

_GET_QUERY = text(
    """
    SELECT
        c.id, c.connection_id, c.provider_config_key, c.config_id, c.environment_id,
        c.tags, c.metadata, c.connection_config, c.credentials, c.credentials_iv,
        c.credentials_tag, c.last_fetched_at, c.created_at, c.updated_at,
        _nango_configs.provider AS provider,
        row_to_json(end_users.*) AS end_user,
        COALESCE(agg.active_logs, '[]'::json) AS active_logs
    FROM _nango_connections c
    JOIN _nango_configs ON _nango_configs.id = c.config_id
    LEFT JOIN end_users ON end_users.id = c.end_user_id
    LEFT JOIN (
        SELECT connection_id,
               json_agg(json_build_object('type', type, 'log_id', log_id)) AS active_logs
        FROM _nango_active_logs
        WHERE active = true
        GROUP BY connection_id
    ) agg ON agg.connection_id = c.id
    WHERE c.connection_id = :connection_id
      AND c.provider_config_key = :provider_config_key
      AND c.environment_id = :environment_id
      AND c.deleted = false
    LIMIT 1
    """
)


class SqlAlchemyConnectionRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        encryption_key: str,
    ) -> None:
        self._session_factory = session_factory
        self._encryption_key = encryption_key

    async def get_connection(
        self,
        *,
        environment_id: int,
        connection_id: str,
        provider_config_key: str,
    ) -> Connection | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    _GET_QUERY,
                    {
                        "connection_id": connection_id,
                        "provider_config_key": provider_config_key,
                        "environment_id": environment_id,
                    },
                )
            ).mappings().first()
        if row is None:
            return None
        return _connection_from_row(
            cast(dict[str, Any], row),
            encryption_key=self._encryption_key,
            decrypt_credentials=True,
        )

    async def update_credentials(
        self,
        *,
        connection_id: int,
        credentials: dict[str, object],
        expires_at: datetime | None,
    ) -> None:
        ct, iv, tag = encrypt_aes_gcm(
            json.dumps(credentials), self._encryption_key
        )
        stored = json.dumps({"encrypted_credentials": ct})
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            await session.execute(
                text(
                    """
                    UPDATE _nango_connections
                    SET credentials = :creds, credentials_iv = :iv,
                        credentials_tag = :tag,
                        credentials_expires_at = :exp,
                        last_refresh_success = :now,
                        refresh_attempts = NULL,
                        refresh_exhausted = false,
                        last_refresh_failure = NULL,
                        updated_at = :now
                    WHERE id = :id
                    """
                ),
                {
                    "creds": stored,
                    "iv": iv,
                    "tag": tag,
                    "exp": expires_at,
                    "now": now,
                    "id": connection_id,
                },
            )
            await session.commit()

    async def upsert_connection(
        self,
        *,
        environment_id: int,
        config_id: int,
        connection_id: str,
        provider_config_key: str,
        credentials: dict[str, object],
        connection_config: dict[str, object],
    ) -> tuple[int, str]:
        ct, iv, tag = encrypt_aes_gcm(
            json.dumps(credentials), self._encryption_key
        )
        stored = json.dumps({"encrypted_credentials": ct})
        now = datetime.now(UTC)

        async with self._session_factory() as session:
            existing = (
                await session.execute(
                    text(
                        """
                        SELECT id FROM _nango_connections
                        WHERE environment_id = :eid AND provider_config_key = :pck
                          AND connection_id = :cid AND deleted = false
                        LIMIT 1
                        """
                    ),
                    {
                        "eid": environment_id,
                        "pck": provider_config_key,
                        "cid": connection_id,
                    },
                )
            ).mappings().first()

            if existing is not None:
                await session.execute(
                    text(
                        """
                        UPDATE _nango_connections
                        SET credentials = :creds, credentials_iv = :iv,
                            credentials_tag = :tag,
                            connection_config = CAST(:cc AS jsonb),
                            updated_at = :now, deleted = false, deleted_at = NULL
                        WHERE id = :id
                        """
                    ),
                    {
                        "creds": stored,
                        "iv": iv,
                        "tag": tag,
                        "cc": json.dumps(connection_config),
                        "now": now,
                        "id": existing["id"],
                    },
                )
                await session.commit()
                return int(existing["id"]), "override"

            row = (
                await session.execute(
                    text(
                        """
                        INSERT INTO _nango_connections
                        (environment_id, config_id, connection_id, provider_config_key,
                         credentials, credentials_iv, credentials_tag,
                         connection_config, tags, deleted)
                        VALUES (:eid, :cfgid, :cid, :pck, :creds, :iv, :tag,
                         CAST(:cc AS jsonb), '{}', false)
                        RETURNING id
                        """
                    ),
                    {
                        "eid": environment_id,
                        "cfgid": config_id,
                        "cid": connection_id,
                        "pck": provider_config_key,
                        "creds": stored,
                        "iv": iv,
                        "tag": tag,
                        "cc": json.dumps(connection_config),
                    },
                )
            ).mappings().one()
            await session.commit()
            return int(row["id"]), "creation"

    async def list_connections(self, filters: ListConnectionsFilters) -> list[Connection]:
        where = ["c.environment_id = :environment_id", "c.deleted = false"]
        params: dict[str, Any] = {"environment_id": filters.environment_id}

        if filters.connection_id is not None:
            where.append("c.connection_id = :connection_id")
            params["connection_id"] = filters.connection_id
        if filters.integration_ids:
            where.append("_nango_configs.unique_key = ANY(:integration_ids)")
            params["integration_ids"] = list(filters.integration_ids)
        if filters.tags:
            where.append("c.tags @> CAST(:tags AS jsonb)")
            params["tags"] = json.dumps(filters.tags)
        if filters.end_user_id is not None:
            where.append("end_users.end_user_id = :end_user_id")
            params["end_user_id"] = filters.end_user_id
        if filters.end_user_organization_id is not None:
            where.append("end_users.organization_id = :end_user_organization_id")
            params["end_user_organization_id"] = filters.end_user_organization_id
        if filters.search is not None:
            where.append(
                "(c.connection_id ILIKE :search_pattern"
                " OR end_users.display_name ILIKE :search_pattern"
                " OR end_users.email ILIKE :search_pattern)"
            )
            params["search_pattern"] = f"%{filters.search}%"

        where_clause = " AND ".join(where)
        query = text(
            f"""
            SELECT
                c.id, c.connection_id, c.provider_config_key, c.config_id,
                c.environment_id, c.tags, c.metadata, c.connection_config,
                c.created_at, c.updated_at,
                _nango_configs.provider AS provider,
                row_to_json(end_users.*) AS end_user,
                COALESCE(agg.active_logs, '[]'::json) AS active_logs
            FROM _nango_connections c
            JOIN _nango_configs ON _nango_configs.id = c.config_id
            LEFT JOIN end_users ON end_users.id = c.end_user_id
            LEFT JOIN (
                SELECT connection_id,
                       json_agg(json_build_object('type', type, 'log_id', log_id)) AS active_logs
                FROM _nango_active_logs
                WHERE active = true
                GROUP BY connection_id
            ) agg ON agg.connection_id = c.id
            WHERE {where_clause}
            ORDER BY c.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        )
        params["limit"] = filters.limit
        params["offset"] = filters.page * filters.limit

        async with self._session_factory() as session:
            rows = (await session.execute(query, params)).mappings().all()
        return [
            _connection_from_row(
                cast(dict[str, Any], row),
                encryption_key=self._encryption_key,
                decrypt_credentials=False,
            )
            for row in rows
        ]


def _connection_from_row(
    row: dict[str, Any],
    *,
    encryption_key: str,
    decrypt_credentials: bool,
) -> Connection:
    return Connection(
        id=_required_int(row, "id"),
        connection_id=_required_str(row, "connection_id"),
        provider_config_key=_required_str(row, "provider_config_key"),
        provider=_required_str(row, "provider"),
        environment_id=_required_int(row, "environment_id"),
        config_id=_optional_int(row, "config_id"),
        tags=_json_object(row.get("tags")),
        metadata=_optional_json_object(row.get("metadata")),
        connection_config=_json_object(row.get("connection_config")),
        credentials=_credentials(row, encryption_key, decrypt_credentials),
        last_fetched_at=_optional_datetime(row, "last_fetched_at"),
        created_at=_required_datetime(row, "created_at"),
        updated_at=_required_datetime(row, "updated_at"),
        end_user=_end_user_from_row(row.get("end_user")),
        active_logs=_active_logs(row.get("active_logs")),
    )


def _credentials(row: dict[str, Any], encryption_key: str, decrypt: bool) -> dict[str, Any]:
    stored = _json_object(row.get("credentials"))
    if not decrypt:
        return {}
    encrypted = stored.get("encrypted_credentials")
    iv = _optional_str(row, "credentials_iv")
    tag = _optional_str(row, "credentials_tag")
    if isinstance(encrypted, str) and iv and tag and encryption_key:
        decrypted = decrypt_aes_gcm(encrypted, iv, tag, encryption_key)
        parsed = json.loads(decrypted)
        if not isinstance(parsed, dict):
            raise RuntimeError("decrypted connection credentials must be a JSON object")
        return cast("dict[str, Any]", parsed)
    return stored


def _end_user_from_row(value: Any) -> ConnectionEndUser | None:
    if not isinstance(value, dict):
        return None
    end_user_id = value.get("end_user_id")
    if not isinstance(end_user_id, str):
        return None
    organization_id = value.get("organization_id")
    organization: ConnectionEndUserOrganization | None = None
    if isinstance(organization_id, str):
        organization = ConnectionEndUserOrganization(
            id=organization_id,
            display_name=_optional_str(value, "organization_display_name"),
        )
    return ConnectionEndUser(
        id=end_user_id,
        email=_optional_str(value, "email"),
        display_name=_optional_str(value, "display_name"),
        tags=_optional_json_object(value.get("tags")),
        organization=organization,
    )


def _active_logs(value: Any) -> list[ConnectionActiveLog]:
    if not isinstance(value, list):
        return []
    logs: list[ConnectionActiveLog] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        type_value = item.get("type")
        log_id = item.get("log_id")
        if isinstance(type_value, str) and isinstance(log_id, str):
            logs.append(ConnectionActiveLog(type=type_value, log_id=log_id))
    return logs


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast("dict[str, Any]", value)
    return {}


def _optional_json_object(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return cast("dict[str, Any]", value)
    return None


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


def _optional_datetime(row: dict[str, Any], key: str) -> datetime | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise RuntimeError(f"expected datetime column: {key}")
    return value