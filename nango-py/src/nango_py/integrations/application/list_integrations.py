"""ListIntegrations use case for ``GET /integrations``.

Authoritative behavior:
``packages/server/lib/controllers/integrations/getListIntegrations.ts`` +
``packages/server/lib/formatters/integration.ts`` (no ``include``).

The api-key path returns every integration config for the environment with no
``allowed_integrations`` filtering (that filter only applies to connect-session
auth, which is a deferred follow-up). Each item is the base public DTO with no
``webhook_url``/``credentials`` keys.
"""

from __future__ import annotations

from dataclasses import dataclass

from nango_py.auth.domain.context import AuthenticatedContext, Scopes
from nango_py.auth.domain.errors import Forbidden
from nango_py.integrations.application.gateway import (
    IntegrationRepository,
    ProviderCatalog,
)
from nango_py.integrations.domain.integration import Integration, PublicIntegrationView
from nango_py.integrations.domain.provider import Provider

LIST_SCOPE = "environment:integrations:list"
LIST_CREDENTIALS_SCOPE = "environment:integrations:list_credentials"
REQUIRED_SCOPES = (LIST_SCOPE, LIST_CREDENTIALS_SCOPE)


@dataclass(frozen=True)
class ListIntegrationsRequest:
    context: AuthenticatedContext


class ListIntegrations:
    def __init__(
        self,
        *,
        integration_repository: IntegrationRepository,
        provider_catalog: ProviderCatalog,
        base_public_url: str,
    ) -> None:
        self._integrations = integration_repository
        self._providers = provider_catalog
        self._base_public_url = base_public_url.rstrip("/")

    async def execute(self, request: ListIntegrationsRequest) -> list[PublicIntegrationView]:
        self._authorize(request.context.scopes)
        integrations = await self._integrations.list_for_environment(
            environment_id=request.context.environment.id
        )
        return [
            self._view(integration, self._providers.get(integration.provider))
            for integration in integrations
        ]

    def _authorize(self, scopes: Scopes) -> None:
        if not scopes.has_any(REQUIRED_SCOPES):
            raise Forbidden(REQUIRED_SCOPES)

    def _view(
        self, integration: Integration, provider: Provider | None
    ) -> PublicIntegrationView:
        display_name = integration.display_name or (provider.display_name if provider else None)
        return PublicIntegrationView(
            unique_key=integration.unique_key,
            provider=integration.provider,
            display_name=display_name or integration.unique_key,
            logo=f"{self._base_public_url}/images/template-logos/{integration.provider}.svg",
            forward_webhooks=integration.forward_webhooks,
            created_at=integration.created_at,
            updated_at=integration.updated_at,
        )