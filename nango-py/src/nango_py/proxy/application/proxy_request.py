"""ProxyRequest use case: resolve connection, build request, execute with retries.

Authoritative behavior:
``packages/shared/lib/services/proxy/request.ts`` (``ProxyRequest.request``) +
``packages/server/lib/controllers/proxy/allProxy.ts``.

Credential refresh on 401: when a 401 is received and a CredentialRefresher is
configured, the proxy refreshes the OAuth2 token and retries with new headers.
Base URL override denylist: checks ``base_url_override`` hostname against a
configured denylist, fail-closed.

The http client is injected by the caller (the route creates a real
``httpx.AsyncClient``; tests inject a mock-transport client).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.connections.application.credential_refresher import CredentialRefresher
from nango_py.connections.application.gateway import ConnectionRepository
from nango_py.integrations.application.gateway import (
    IntegrationRepository,
    ProviderCatalog,
)
from nango_py.proxy.domain.config import ProxyConfig
from nango_py.proxy.domain.denylist import is_base_url_override_denied
from nango_py.proxy.domain.errors import ProxyError
from nango_py.proxy.domain.headers import build_proxy_headers
from nango_py.proxy.domain.retry import backoff_wait, get_proxy_retry_from_err
from nango_py.proxy.domain.url import build_proxy_url

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ProxyRequestInput:
    context: AuthenticatedContext
    connection_id: str
    provider_config_key: str
    method: str
    endpoint: str
    forwarded_headers: dict[str, str] = None  # type: ignore[assignment]
    data: bytes | None = None
    retries: int = 0
    base_url_override: str | None = None
    decompress: bool = False
    retry_on: tuple[int, ...] = ()
    forward_headers_on_redirect: bool = True


@dataclass(frozen=True)
class ProxyResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class ProxyRequest:
    """Use case for ``/proxy/*splat``.

    Resolves integration + connection, builds URL + headers, and executes the
    upstream request with retries. Returns the upstream response (success or
    error — both passthrough). Raises :class:`ProxyError` for config/connection
    failures and exhausted network errors.
    """

    def __init__(
        self,
        *,
        connection_repository: ConnectionRepository,
        integration_repository: IntegrationRepository,
        provider_catalog: ProviderCatalog,
        credential_refresher: CredentialRefresher | None = None,
        base_url_override_denylist: set[str] | None = None,
    ) -> None:
        self._connections = connection_repository
        self._integrations = integration_repository
        self._providers = provider_catalog
        self._refresher = credential_refresher
        self._denylist = base_url_override_denylist or set()

    async def execute(
        self,
        request: ProxyRequestInput,
        http_client: httpx.AsyncClient,
    ) -> ProxyResponse:
        integration = await self._integrations.get_by_unique_key(
            environment_id=request.context.environment.id,
            unique_key=request.provider_config_key,
        )
        if integration is None:
            raise ProxyError(
                "unknown_provider_config",
                (
                    "Provider config not found for the given provider config key."
                    " Please make sure the provider config exists in the Nango dashboard."
                ),
                status=404,
            )

        connection = await self._connections.get_connection(
            environment_id=request.context.environment.id,
            connection_id=request.connection_id,
            provider_config_key=request.provider_config_key,
        )
        if connection is None:
            raise ProxyError("server_error", "Failed to get connection", status=400)

        if self._refresher is not None:
            connection = await self._refresher.refresh_if_needed(
                connection, integration, http_client=http_client
            )

        provider_entry = self._providers.entry(integration.provider)
        if provider_entry is None:
            raise ProxyError("unknown_provider", "Unknown provider", status=400)
        proxy = provider_entry.get("proxy")
        if not isinstance(proxy, dict):
            proxy = {}
        if not proxy.get("base_url") and not request.base_url_override:
            raise ProxyError(
                "unsupported_provider", "Provider does not support proxy", status=400
            )

        if request.base_url_override and is_base_url_override_denied(
            request.base_url_override, self._denylist
        ):
            raise ProxyError(
                "base_url_override_denied",
                "Base URL override is not allowed for this hostname",
                status=403,
            )

        config = ProxyConfig(
            endpoint=request.endpoint,
            method=request.method,
            provider_entry=provider_entry,
            provider_name=integration.provider,
            provider_config_key=request.provider_config_key,
            headers=request.forwarded_headers or {},
            data=request.data,
            retries=request.retries,
            base_url_override=request.base_url_override,
            decompress=request.decompress,
            retry_on=request.retry_on,
            forward_headers_on_redirect=request.forward_headers_on_redirect,
        )

        url = build_proxy_url(
            config,
            credentials=connection.credentials,
            connection_config=connection.connection_config,
        )
        headers = build_proxy_headers(
            config,
            url=url,
            credentials=connection.credentials,
            connection_config=connection.connection_config,
            integration_config={
                "oauth_client_id": integration.oauth_client_id or "",
                "oauth_client_secret": integration.oauth_client_secret or "",
            },
        )

        return await self._execute_with_retries(
            http_client, config, url, headers, request.data,
            connection=connection, integration=integration,
        )

    async def _execute_with_retries(
        self,
        client: httpx.AsyncClient,
        config: ProxyConfig,
        url: str,
        headers: dict[str, str],
        data: bytes | None,
        *,
        connection: Any = None,
        integration: Any = None,
    ) -> ProxyResponse:
        max_attempts = config.retries + 1
        last_response: ProxyResponse | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.send(
                    httpx.Request(config.method, url, headers=headers, content=data),
                    follow_redirects=True,
                )
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < max_attempts:
                    await asyncio.sleep(backoff_wait(attempt))
                    continue
                raise ProxyError("network_error", str(exc), status=502) from exc

            if 200 <= response.status_code < 400:
                return ProxyResponse(
                    status=response.status_code,
                    headers=dict(response.headers),
                    body=response.content,
                )

            retry_reason = get_proxy_retry_from_err(
                status=response.status_code,
                headers=dict(response.headers),
                proxy_config=config,
                retry_on=config.retry_on,
            )
            if retry_reason.retry and attempt < max_attempts:
                # On 401, try refreshing credentials before retrying
                if (
                    response.status_code == 401
                    and self._refresher is not None
                    and connection is not None
                    and integration is not None
                ):
                    try:
                        connection = await self._refresher.refresh_if_needed(
                            connection, integration, http_client=client
                        )
                        headers = build_proxy_headers(
                            config,
                            url=url,
                            credentials=connection.credentials,
                            connection_config=connection.connection_config,
                            integration_config={
                                "oauth_client_id": integration.oauth_client_id or "",
                                "oauth_client_secret": integration.oauth_client_secret or "",
                            },
                        )
                    except Exception:
                        pass
                await asyncio.sleep(backoff_wait(attempt))
                continue

            last_response = ProxyResponse(
                status=response.status_code,
                headers=dict(response.headers),
                body=response.content,
            )
            return last_response

        if last_response is not None:
            return last_response
        raise ProxyError("unknown_error", "Unexpected end of retry loop")