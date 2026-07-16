"""E2e test for OAuth2 credential refresh via the proxy.

Seeds a connection with expired OAuth2 credentials, mocks the provider's token
endpoint to return fresh credentials, and verifies the proxy uses the refreshed
access_token for the upstream call.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, MockTransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.server.app import create_app
from tests.integration._seeds import (
    DEFAULT_KEY,
    DEFAULT_TEST_KEY,
    seed_full_auth,
    seed_integration,
)
from tests.integration._seeds_connections import seed_connection

BASE_PUBLIC_URL = "https://public.test"
_EXPIRED_CREDS: dict[str, object] = {
    "type": "OAUTH2",
    "access_token": "old-expired-token",
    "refresh_token": "refresh-xyz",
    "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
    "raw": {},
}
_NEW_ACCESS_TOKEN = "fresh-access-token-999"


@pytest.fixture
async def app_and_factory(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> tuple[Any, async_sessionmaker[AsyncSession]]:
    return (
        create_app(
            session_factory=db_session_factory,
            encryption_key=DEFAULT_KEY,
            base_public_url=BASE_PUBLIC_URL,
            webhook_receive_url="https://webhook.test",
        ),
        db_session_factory,
    )


def _client(app: Any) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_proxy_refreshes_expired_oauth2_token(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await seed_full_auth(factory, scopes=["environment:proxy"])
    config_id = await seed_integration(
        factory, environment_id=env_id, unique_key="github", provider="github"
    )
    await seed_connection(
        factory,
        environment_id=env_id,
        config_id=config_id,
        connection_id="conn-1",
        provider_config_key="github",
        credentials=_EXPIRED_CREDS,
        tags={},
    )

    token_refresh_called = False
    upstream_captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_refresh_called
        if "login/oauth/access_token" in str(request.url):
            token_refresh_called = True
            return httpx.Response(
                200,
                json={
                    "access_token": _NEW_ACCESS_TOKEN,
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "refresh_token": "new-refresh-abc",
                },
            )
        upstream_captured.append(request)
        return httpx.Response(200, json={"ok": True})

    app.state.httpx_transport = MockTransport(handler)

    async with _client(app) as client:
        response = await client.get(
            "/proxy/repos/octocat/hello",
            headers={
                "Authorization": f"Bearer {DEFAULT_TEST_KEY}",
                "provider-config-key": "github",
                "connection-id": "conn-1",
            },
        )

    assert response.status_code == 200
    assert token_refresh_called is True
    assert len(upstream_captured) == 1
    assert upstream_captured[0].headers["authorization"] == f"Bearer {_NEW_ACCESS_TOKEN}"


async def test_proxy_skips_refresh_for_fresh_credentials(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await seed_full_auth(factory, scopes=["environment:proxy"])
    config_id = await seed_integration(
        factory, environment_id=env_id, unique_key="github", provider="github"
    )
    fresh_creds: dict[str, object] = {
        "type": "OAUTH2",
        "access_token": "still-fresh-token",
        "refresh_token": "refresh-xyz",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "raw": {},
    }
    await seed_connection(
        factory,
        environment_id=env_id,
        config_id=config_id,
        connection_id="conn-1",
        provider_config_key="github",
        credentials=fresh_creds,
        tags={},
    )

    token_refresh_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_refresh_called
        if "login/oauth/access_token" in str(request.url):
            token_refresh_called = True
            return httpx.Response(200, json={"access_token": "should-not-happen"})
        return httpx.Response(200, json={"ok": True})

    app.state.httpx_transport = MockTransport(handler)

    async with _client(app) as client:
        response = await client.get(
            "/proxy/repos/octocat/hello",
            headers={
                "Authorization": f"Bearer {DEFAULT_TEST_KEY}",
                "provider-config-key": "github",
                "connection-id": "conn-1",
            },
        )

    assert response.status_code == 200
    assert token_refresh_called is False