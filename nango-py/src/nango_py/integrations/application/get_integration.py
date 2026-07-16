"""GetIntegration use case.

Orchestrates the ``GET /integrations/:uniqueKey`` boundary:
authorization scope check, integration lookup, provider resolution, and
public response view assembly with credential visibility policy.

Authoritative TypeScript behavior:
``packages/server/lib/controllers/integrations/uniqueKey/getIntegration.ts`` +
``packages/server/lib/formatters/integration.ts``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from nango_py.auth.domain.context import AuthenticatedContext, Scopes
from nango_py.auth.domain.errors import Forbidden
from nango_py.integrations.application.gateway import (
    IntegrationRepository,
    ProviderCatalog,
)
from nango_py.integrations.domain.errors import IntegrationNotFound, ProviderNotFound
from nango_py.integrations.domain.integration import (
    NOT_SET,
    AppCredentials,
    CredentialsView,
    Integration,
    OAuthCredentials,
    PublicIntegrationView,
    _NotSet,
)
from nango_py.integrations.domain.provider import Provider

READ_SCOPE = "environment:integrations:read"
READ_CREDENTIALS_SCOPE = "environment:integrations:read_credentials"
REQUIRED_SCOPES = (READ_SCOPE, READ_CREDENTIALS_SCOPE)

IncludeKey = Literal["webhook", "credentials"]

#: Auth modes that surface OAuth-style credentials in the public response.
OAUTH_AUTH_MODES = frozenset({"OAUTH1", "OAUTH2", "TBA"})
APP_AUTH_MODE = "APP"


@dataclass(frozen=True)
class GetIntegrationRequest:
    unique_key: str
    include: frozenset[IncludeKey]
    context: AuthenticatedContext


class GetIntegration:
    """Use case for ``GET /integrations/:uniqueKey``.

    Dependencies are injected; the use case owns authorization, lookup, and
    response-shape policy. It does not know about HTTP or SQLAlchemy.
    """

    def __init__(
        self,
        *,
        integration_repository: IntegrationRepository,
        provider_catalog: ProviderCatalog,
        base_public_url: str,
        webhook_receive_url: str,
    ) -> None:
        self._integrations = integration_repository
        self._providers = provider_catalog
        self._base_public_url = base_public_url.rstrip("/")
        self._webhook_receive_url = webhook_receive_url.rstrip("/")

    async def execute(self, request: GetIntegrationRequest) -> PublicIntegrationView:
        self._authorize(request.context.scopes)

        integration = await self._integrations.get_by_unique_key(
            environment_id=request.context.environment.id,
            unique_key=request.unique_key,
        )
        if integration is None:
            raise IntegrationNotFound(request.unique_key)

        provider = self._providers.get(integration.provider)
        if provider is None:
            raise ProviderNotFound(integration.provider)

        return self._build_view(integration, provider, request)

    def _authorize(self, scopes: Scopes) -> None:
        if not scopes.has_any(REQUIRED_SCOPES):
            raise Forbidden(REQUIRED_SCOPES)

    def _build_view(
        self,
        integration: Integration,
        provider: Provider,
        request: GetIntegrationRequest,
    ) -> PublicIntegrationView:
        webhook_url: str | None | _NotSet = NOT_SET
        if "webhook" in request.include:
            webhook_url = self._webhook_url(integration, provider, request.context)

        credentials: CredentialsView | None | _NotSet = NOT_SET
        if "credentials" in request.include and request.context.scopes.has(READ_CREDENTIALS_SCOPE):
            credentials = self._credentials_view(integration, provider)

        return PublicIntegrationView(
            unique_key=integration.unique_key,
            provider=integration.provider,
            display_name=integration.display_name or provider.display_name,
            logo=f"{self._base_public_url}/images/template-logos/{integration.provider}.svg",
            forward_webhooks=integration.forward_webhooks,
            created_at=integration.created_at,
            updated_at=integration.updated_at,
            webhook_url=webhook_url,
            credentials=credentials,
        )

    def _webhook_url(
        self,
        integration: Integration,
        provider: Provider,
        context: AuthenticatedContext,
    ) -> str | None:
        if not provider.webhook_routing_script:
            return None
        return (
            f"{self._webhook_receive_url}"
            f"/{context.environment.uuid}"
            f"/{integration.provider}"
        )

    def _credentials_view(
        self,
        integration: Integration,
        provider: Provider,
    ) -> CredentialsView | None:
        if provider.auth_mode in OAUTH_AUTH_MODES:
            shared = integration.shared_credentials_id is not None
            return OAuthCredentials(
                type=provider.auth_mode,
                client_id="" if shared else (integration.oauth_client_id or ""),
                client_secret="" if shared else (integration.oauth_client_secret or ""),
                scopes=integration.oauth_scopes or None,
                webhook_secret=self._webhook_secret(integration.custom),
            )
        if provider.auth_mode == APP_AUTH_MODE:
            return AppCredentials(
                type=APP_AUTH_MODE,
                app_id=integration.oauth_client_id or "",
                private_key=integration.oauth_client_secret or "",
                app_link=integration.app_link or None,
            )
        return None

    @staticmethod
    def _webhook_secret(custom: Mapping[str, object] | None) -> str | None:
        if not custom:
            return None
        value = custom.get("webhookSecret")
        return value if isinstance(value, str) else None
