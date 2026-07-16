"""ListConnections use case for ``GET /connections``.

Authoritative behavior:
``packages/server/lib/controllers/connection/getConnections.ts`` +
``packages/server/lib/formatters/connection.ts`` (``connectionSimpleToPublicApi``).

The api-key path returns every connection for the environment matching the
filters, ordered by ``created_at DESC``. List items never include credentials.
"""

from __future__ import annotations

from dataclasses import dataclass

from nango_py.auth.domain.context import AuthenticatedContext, Scopes
from nango_py.auth.domain.errors import Forbidden
from nango_py.connections.application.gateway import (
    ConnectionRepository,
    ListConnectionsFilters,
)
from nango_py.connections.domain.connection import Connection, ConnectionListItem
from nango_py.shared.serialize import iso_required

LIST_SCOPE = "environment:connections:list"
LIST_CREDENTIALS_SCOPE = "environment:connections:list_credentials"
REQUIRED_SCOPES = (LIST_SCOPE, LIST_CREDENTIALS_SCOPE)
DEFAULT_LIMIT = 10_000
MAX_LIMIT = 2000


@dataclass(frozen=True)
class ListConnectionsRequest:
    context: AuthenticatedContext
    connection_id: str | None = None
    integration_ids: tuple[str, ...] = ()
    search: str | None = None
    end_user_id: str | None = None
    end_user_organization_id: str | None = None
    tags: dict[str, str] | None = None
    limit: int = DEFAULT_LIMIT
    page: int = 0


class ListConnections:
    def __init__(self, *, connection_repository: ConnectionRepository) -> None:
        self._repo = connection_repository

    async def execute(self, request: ListConnectionsRequest) -> list[ConnectionListItem]:
        self._authorize(request.context.scopes)
        connections = await self._repo.list_connections(
            ListConnectionsFilters(
                environment_id=request.context.environment.id,
                connection_id=request.connection_id,
                integration_ids=request.integration_ids,
                search=request.search,
                end_user_id=request.end_user_id,
                end_user_organization_id=request.end_user_organization_id,
                tags=request.tags,
                limit=request.limit,
                page=request.page,
            )
        )
        return [self._to_item(connection) for connection in connections]

    def _authorize(self, scopes: Scopes) -> None:
        if not scopes.has_any(REQUIRED_SCOPES):
            raise Forbidden(REQUIRED_SCOPES)

    @staticmethod
    def _to_item(connection: Connection) -> ConnectionListItem:
        return ConnectionListItem(
            id=connection.id,
            connection_id=connection.connection_id,
            provider_config_key=connection.provider_config_key,
            provider=connection.provider,
            errors=connection.active_logs,
            end_user=connection.end_user,
            tags=connection.tags,
            metadata=connection.metadata,
            created=iso_required(connection.created_at),
        )