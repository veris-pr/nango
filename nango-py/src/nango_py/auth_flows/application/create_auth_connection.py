"""CreateAuthConnection use case: create/update a connection with credentials.

Shared by all simple auth mode endpoints (API_KEY, BASIC, NONE). Each endpoint
builds the credentials dict for its mode, then calls this use case.

Authoritative behavior:
``packages/server/lib/controllers/auth/postApiKey.ts``,
``postBasic.ts``, ``postUnauthenticated.ts``.

Deferred: credential testing (calling the provider API to verify),
connect-session auth, HMAC check, connection validation hooks, webhooks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth_flows.domain.errors import (
    InvalidAuthMode,
    UnknownIntegrationConfig,
    UnknownProviderTemplate,
)
from nango_py.connections.application.gateway import ConnectionRepository
from nango_py.integrations.application.gateway import (
    IntegrationRepository,
    ProviderCatalog,
)

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class CreateAuthConnectionRequest:
    context: AuthenticatedContext
    provider_config_key: str
    connection_id: str | None = None
    credentials: JsonObject | None = None
    connection_config: JsonObject | None = None
    expected_auth_mode: str = ""


@dataclass(frozen=True)
class CreateAuthConnectionResult:
    connection_id: str
    provider_config_key: str
    operation: str  # "creation" | "override"


class CreateAuthConnection:
    def __init__(
        self,
        *,
        connection_repository: ConnectionRepository,
        integration_repository: IntegrationRepository,
        provider_catalog: ProviderCatalog,
    ) -> None:
        self._connections = connection_repository
        self._integrations = integration_repository
        self._providers = provider_catalog

    async def execute(
        self, request: CreateAuthConnectionRequest
    ) -> CreateAuthConnectionResult:
        integration = await self._integrations.get_by_unique_key(
            environment_id=request.context.environment.id,
            unique_key=request.provider_config_key,
        )
        if integration is None:
            raise UnknownIntegrationConfig()

        provider_entry = self._providers.entry(integration.provider)
        if provider_entry is None:
            raise UnknownProviderTemplate()

        actual_auth_mode = str(provider_entry.get("auth_mode") or "")
        if request.expected_auth_mode and actual_auth_mode != request.expected_auth_mode:
            raise InvalidAuthMode()

        connection_id = request.connection_id or str(uuid.uuid4())
        credentials = request.credentials or {}
        connection_config = request.connection_config or {}

        _, operation = await self._connections.upsert_connection(
            environment_id=request.context.environment.id,
            config_id=integration.id or 0,
            connection_id=connection_id,
            provider_config_key=request.provider_config_key,
            credentials=credentials,
            connection_config=connection_config,
        )

        return CreateAuthConnectionResult(
            connection_id=connection_id,
            provider_config_key=request.provider_config_key,
            operation=operation,
        )