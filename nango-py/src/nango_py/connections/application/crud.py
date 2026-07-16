"""Connection CRUD + metadata use cases.

Mirrors:
- POST /connections — create connection with credentials
- PATCH /connections/:connectionId — update end_user/tags
- DELETE /connections/:connectionId — soft-delete + orchestrator cleanup
- POST/PATCH /connections/metadata — batch set/update metadata
- Deprecated /connection routes (same handlers, different paths)

Auth: apiAuth + environment:connections:write scope.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.domain.errors import Forbidden
from nango_py.connections.domain.errors import UnknownProviderConfig
from nango_py.integrations.application.gateway import (
    IntegrationRepository,
    ProviderCatalog,
)

JsonObject = dict[str, Any]
WRITE_SCOPE = "environment:connections:write"


@dataclass(frozen=True)
class CreateConnectionRequest:
    context: AuthenticatedContext
    provider_config_key: str
    connection_id: str | None = None
    credentials: JsonObject | None = None
    metadata: JsonObject | None = None
    connection_config: JsonObject | None = None
    tags: dict[str, str] | None = None


@dataclass(frozen=True)
class PatchConnectionRequest:
    context: AuthenticatedContext
    connection_id: str
    provider_config_key: str
    tags: dict[str, str] | None = None


@dataclass(frozen=True)
class DeleteConnectionRequest:
    context: AuthenticatedContext
    connection_id: str
    provider_config_key: str


@dataclass(frozen=True)
class SetMetadataRequest:
    context: AuthenticatedContext
    connection_ids: list[str]
    provider_config_key: str
    metadata: JsonObject


class ConnectionCrudService:
    """Create, update, delete connections + metadata."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        integration_repository: IntegrationRepository,
        provider_catalog: ProviderCatalog,
        encryption_key: str = "",
    ) -> None:
        self._sf = session_factory
        self._integrations = integration_repository
        self._providers = provider_catalog
        self._encryption_key = encryption_key

    async def create(self, request: CreateConnectionRequest) -> JsonObject:
        _check_scope(request.context)

        integration = await self._integrations.get_by_unique_key(
            environment_id=request.context.environment.id,
            unique_key=request.provider_config_key,
        )
        if integration is None:
            raise UnknownProviderConfig()

        connection_id = request.connection_id or str(uuid.uuid4())
        now = datetime.now(UTC)

        # Encrypt credentials
        creds_json = json.dumps(request.credentials or {})
        creds_stored = creds_json
        creds_iv = None
        creds_tag = None
        if self._encryption_key and request.credentials:
            from nango_py.shared.crypto import encrypt_aes_gcm

            ct, iv, tag = encrypt_aes_gcm(creds_json, self._encryption_key)
            creds_stored = json.dumps({"encrypted_credentials": ct})
            creds_iv = iv
            creds_tag = tag

        async with self._sf() as session:
            # Check existing
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
                        "eid": request.context.environment.id,
                        "pck": request.provider_config_key,
                        "cid": connection_id,
                    },
                )
            ).mappings().first()

            if existing:
                # Update existing
                await session.execute(
                    text(
                        """
                        UPDATE _nango_connections SET
                            credentials = CAST(:creds AS json),
                            credentials_iv = :iv, credentials_tag = :tag,
                            metadata = CAST(:meta AS jsonb),
                            connection_config = CAST(:cc AS jsonb),
                            tags = CAST(:tags AS jsonb),
                            updated_at = :now, deleted = false, deleted_at = NULL
                        WHERE id = :id
                        """
                    ),
                    {
                        "creds": creds_stored, "iv": creds_iv, "tag": creds_tag,
                        "meta": json.dumps(request.metadata) if request.metadata else None,
                        "cc": json.dumps(request.connection_config or {}),
                        "tags": json.dumps(request.tags or {}),
                        "now": now, "id": existing["id"],
                    },
                )
                conn_id = existing["id"]
                operation = "override"
            else:
                # Insert new
                row = (
                    await session.execute(
                        text(
                            """
                            INSERT INTO _nango_connections
                            (environment_id, config_id, connection_id, provider_config_key,
                             credentials, credentials_iv, credentials_tag,
                             connection_config, metadata, tags, deleted, created_at, updated_at)
                            VALUES (:eid, :cfgid, :cid, :pck,
                             CAST(:creds AS json), :iv, :tag,
                             CAST(:cc AS jsonb), CAST(:meta AS jsonb),
                             CAST(:tags AS jsonb), false, :now, :now)
                            RETURNING id
                            """
                        ),
                        {
                            "eid": request.context.environment.id,
                            "cfgid": integration.id,
                            "cid": connection_id,
                            "pck": request.provider_config_key,
                            "creds": creds_stored, "iv": creds_iv, "tag": creds_tag,
                            "cc": json.dumps(request.connection_config or {}),
                            "meta": json.dumps(request.metadata) if request.metadata else None,
                            "tags": json.dumps(request.tags or {}),
                            "now": now,
                        },
                    )
                ).mappings().first()
                conn_id = row["id"] if row else 0
                operation = "creation"
            await session.commit()

        return {
            "id": conn_id,
            "connection_id": connection_id,
            "provider_config_key": request.provider_config_key,
            "operation": operation,
        }

    async def patch(self, request: PatchConnectionRequest) -> bool:
        _check_scope(request.context)
        now = datetime.now(UTC)

        async with self._sf() as session:
            result = await session.execute(
                text(
                    """
                    UPDATE _nango_connections SET
                        tags = CAST(:tags AS jsonb),
                        updated_at = :now
                    WHERE environment_id = :eid AND provider_config_key = :pck
                      AND connection_id = :cid AND deleted = false
                    RETURNING id
                    """
                ),
                {
                    "tags": json.dumps(request.tags or {}),
                    "now": now,
                    "eid": request.context.environment.id,
                    "pck": request.provider_config_key,
                    "cid": request.connection_id,
                },
            )
            await session.commit()

        return result.scalar() is not None

    async def delete(self, request: DeleteConnectionRequest) -> bool:
        _check_scope(request.context)
        now = datetime.now(UTC)

        async with self._sf() as session:
            result = await session.execute(
                text(
                    """
                    UPDATE _nango_connections SET
                        deleted = true, deleted_at = :now, updated_at = :now
                    WHERE environment_id = :eid AND provider_config_key = :pck
                      AND connection_id = :cid AND deleted = false
                    RETURNING id
                    """
                ),
                {
                    "now": now,
                    "eid": request.context.environment.id,
                    "pck": request.provider_config_key,
                    "cid": request.connection_id,
                },
            )
            await session.commit()

        return result.scalar() is not None

    async def set_metadata(self, request: SetMetadataRequest) -> int:
        _check_scope(request.context)
        now = datetime.now(UTC)
        updated = 0

        async with self._sf() as session:
            for cid in request.connection_ids:
                result = await session.execute(
                    text(
                        """
                        UPDATE _nango_connections SET
                            metadata = CAST(:meta AS jsonb),
                            updated_at = :now
                        WHERE environment_id = :eid AND provider_config_key = :pck
                          AND connection_id = :cid AND deleted = false
                        RETURNING id
                        """
                    ),
                    {
                        "meta": json.dumps(request.metadata),
                        "now": now,
                        "eid": request.context.environment.id,
                        "pck": request.provider_config_key,
                        "cid": cid,
                    },
                )
                updated += len(result.fetchall())
            await session.commit()

        return updated

    async def update_metadata(self, request: SetMetadataRequest) -> int:
        """Patch metadata (merge existing with new)."""
        _check_scope(request.context)
        now = datetime.now(UTC)
        updated = 0

        async with self._sf() as session:
            for cid in request.connection_ids:
                result = await session.execute(
                    text(
                        """
                        UPDATE _nango_connections SET
                            metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:meta AS jsonb),
                            updated_at = :now
                        WHERE environment_id = :eid AND provider_config_key = :pck
                          AND connection_id = :cid AND deleted = false
                        RETURNING id
                        """
                    ),
                    {
                        "meta": json.dumps(request.metadata),
                        "now": now,
                        "eid": request.context.environment.id,
                        "pck": request.provider_config_key,
                        "cid": cid,
                    },
                )
                updated += len(result.fetchall())
            await session.commit()

        return updated


def _check_scope(context: AuthenticatedContext) -> None:
    if not context.scopes.has(WRITE_SCOPE):
        raise Forbidden((WRITE_SCOPE,))