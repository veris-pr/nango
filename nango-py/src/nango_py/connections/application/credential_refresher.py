"""CredentialRefresher: OAuth2 token refresh orchestration.

Mirrors the core of ``refreshOrTestCredentials`` +
``refreshCredentialsIfNeeded`` in
``packages/shared/lib/services/connections/credentials/refresh.ts``.

Phase 5b scope: OAUTH2 standard refresh_token grant. Deferred: per-provider
custom refresh implementations, token introspection, distributed locking,
in-flight deduplication, github-app JWT refresh, TWO_STEP/JWT/APP refresh.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import httpx

from nango_py.connections.application.gateway import ConnectionRepository
from nango_py.connections.domain.connection import Connection
from nango_py.connections.domain.refresh import (
    get_expires_at_from_credentials,
    parse_raw_credentials,
    should_refresh,
)
from nango_py.integrations.application.gateway import (
    ProviderCatalog,
)
from nango_py.proxy.domain.interpolate import interpolate

JsonObject = dict[str, Any]


class CredentialRefresher:
    """Refresh OAUTH2 credentials if expired or forced."""

    def __init__(
        self,
        *,
        connection_repository: ConnectionRepository,
        provider_catalog: ProviderCatalog,
    ) -> None:
        self._connections = connection_repository
        self._providers = provider_catalog

    async def refresh_if_needed(
        self,
        connection: Connection,
        integration: Any,
        *,
        instant_refresh: bool = False,
        http_client: httpx.AsyncClient,
    ) -> Connection:
        provider_entry = self._providers.entry(integration.provider)
        if provider_entry is None:
            return connection

        should, _reason = should_refresh(
            connection.credentials,
            instant_refresh=instant_refresh,
            provider_entry=provider_entry,
        )
        if not should:
            return connection

        token_url = provider_entry.get("token_url") or provider_entry.get("refresh_url")
        if not token_url or not isinstance(token_url, str):
            return connection

        interpolated_url = interpolate(
            token_url,
            {"connectionConfig": connection.connection_config},
        )

        refresh_token = connection.credentials.get("refresh_token")
        client_id = integration.oauth_client_id or ""
        client_secret = integration.oauth_client_secret or ""

        try:
            response = await http_client.post(
                interpolated_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Token refresh HTTP error: {exc}") from exc

        if response.status_code != 200:
            raise RuntimeError(
                f"Token refresh failed with status {response.status_code}"
            )

        raw = response.json()
        new_credentials = parse_raw_credentials(
            raw,
            old_refresh_token=refresh_token if isinstance(refresh_token, str) else None,
        )

        expires_at = get_expires_at_from_credentials(new_credentials)
        await self._connections.update_credentials(
            connection_id=connection.id,
            credentials=new_credentials,
            expires_at=expires_at,
        )

        return replace(connection, credentials=new_credentials)