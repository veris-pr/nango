"""GetConnection use case for ``GET /connections/:connectionId``.

Authoritative behavior:
``packages/server/lib/controllers/connection/connectionId/getConnection.ts`` +
``packages/server/lib/formatters/connection.ts`` (``connectionFullToPublicApi``).

Credential refresh / token refresh / github-app JWT / the ``invalid_credentials``
error are deferred to the auth-flows phase. This read path returns the stored
(decrypted) credentials with refresh_token stripping and credential-visibility
scope enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass

from nango_py.auth.domain.context import AuthenticatedContext, Scopes
from nango_py.auth.domain.errors import Forbidden
from nango_py.connections.application.gateway import ConnectionRepository
from nango_py.connections.domain.connection import ConnectionFull
from nango_py.connections.domain.credentials import strip_refresh_token
from nango_py.connections.domain.errors import ConnectionNotFound, UnknownProviderConfig
from nango_py.integrations.application.gateway import IntegrationRepository
from nango_py.shared.serialize import iso, iso_required

READ_SCOPE = "environment:connections:read"
READ_CREDENTIALS_SCOPE = "environment:connections:read_credentials"
REQUIRED_SCOPES = (READ_SCOPE, READ_CREDENTIALS_SCOPE)
EMPTY_CREDENTIALS: dict[str, object] = {}


@dataclass(frozen=True)
class GetConnectionRequest:
    context: AuthenticatedContext
    connection_id: str
    provider_config_key: str
    return_refresh_token: bool = False


class GetConnection:
    def __init__(
        self,
        *,
        connection_repository: ConnectionRepository,
        integration_repository: IntegrationRepository,
    ) -> None:
        self._connections = connection_repository
        self._integrations = integration_repository

    async def execute(self, request: GetConnectionRequest) -> ConnectionFull:
        self._authorize(request.context.scopes)

        integration = await self._integrations.get_by_unique_key(
            environment_id=request.context.environment.id,
            unique_key=request.provider_config_key,
        )
        if integration is None:
            raise UnknownProviderConfig()

        connection = await self._connections.get_connection(
            environment_id=request.context.environment.id,
            connection_id=request.connection_id,
            provider_config_key=request.provider_config_key,
        )
        if connection is None:
            raise ConnectionNotFound()

        include_credentials = request.context.scopes.has(READ_CREDENTIALS_SCOPE)
        if include_credentials:
            credentials = strip_refresh_token(
                connection.credentials, return_refresh_token=request.return_refresh_token
            )
        else:
            credentials = dict(EMPTY_CREDENTIALS)

        return ConnectionFull(
            id=connection.id,
            connection_id=connection.connection_id,
            provider_config_key=connection.provider_config_key,
            provider=connection.provider,
            errors=connection.active_logs,
            end_user=connection.end_user,
            tags=connection.tags,
            metadata=connection.metadata,
            connection_config=connection.connection_config,
            created_at=iso_required(connection.created_at),
            updated_at=iso_required(connection.updated_at),
            last_fetched_at=iso(connection.last_fetched_at),
            credentials=credentials,
        )

    def _authorize(self, scopes: Scopes) -> None:
        if not scopes.has_any(REQUIRED_SCOPES):
            raise Forbidden(REQUIRED_SCOPES)