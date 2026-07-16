"""E2e tests for auth flow endpoints: API key, basic, unauthenticated, OAuth2 connect + callback."""

from __future__ import annotations

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

BASE_PUBLIC_URL = "https://public.test"


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


async def _seed(
    factory: async_sessionmaker[AsyncSession],
    *,
    provider: str,
    unique_key: str,
    scopes: list[str] | None = None,
) -> int:
    env_id, _ = await seed_full_auth(factory, scopes=scopes or ["environment:*"])
    await seed_integration(
        factory, environment_id=env_id, unique_key=unique_key, provider=provider,
        oauth_client_id="test-client-id", oauth_client_secret="test-client-secret",
    )
    return env_id


async def test_api_key_auth_creates_connection(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed(factory, provider="1password-scim", unique_key="1password-scim")

    async with _client(app) as client:
        response = await client.post(
            "/api-auth/api-key/1password-scim?connection_id=conn-test",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={"apiKey": "test-api-key-123"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "connectionId": "conn-test",
        "providerConfigKey": "1password-scim",
    }


async def test_basic_auth_creates_connection(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed(factory, provider="addepar-basic", unique_key="addepar-basic")

    async with _client(app) as client:
        response = await client.post(
            "/api-auth/basic/addepar-basic?connection_id=conn-basic",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={"username": "myuser", "password": "mypass"},
        )

    assert response.status_code == 200
    assert response.json()["connectionId"] == "conn-basic"


async def test_unauthenticated_auth_creates_connection(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed(factory, provider="unauthenticated", unique_key="unauthenticated")

    async with _client(app) as client:
        response = await client.post(
            "/auth/unauthenticated/unauthenticated?connection_id=conn-none",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert response.status_code == 200
    assert response.json()["connectionId"] == "conn-none"


async def test_api_key_wrong_auth_mode_rejected(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed(factory, provider="github", unique_key="github")

    async with _client(app) as client:
        response = await client.post(
            "/api-auth/api-key/github?connection_id=conn-wrong",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={"apiKey": "test-key"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_auth_mode"


async def test_oauth_connect_redirects(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed(factory, provider="github", unique_key="github")

    async with _client(app) as client:
        response = await client.get(
            "/oauth/connect/github?connection_id=conn-oauth",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "github.com/login/oauth/authorize" in location
    assert "client_id=test-client-id" in location
    assert "response_type=code" in location
    assert "state=" in location


async def test_oauth_callback_exchanges_code_and_creates_connection(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed(factory, provider="github", unique_key="github")
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "access_token": "gho_new_token",
                "token_type": "bearer",
                "expires_in": 3600,
                "refresh_token": "gho_refresh",
                "scope": "repo",
            },
        )

    app.state.httpx_transport = MockTransport(handler)

    import base64
    import json as _json

    state = base64.urlsafe_b64encode(
        _json.dumps({
            "connectionId": "conn-callback",
            "providerConfigKey": "github",
            "environmentId": 1,
        }).encode()
    ).decode()

    async with _client(app) as client:
        response = await client.get(
            f"/oauth/callback/github?code=test-code&state={state}",
        )

    assert response.status_code == 200
    assert response.json()["connectionId"] == "conn-callback"
    assert len(captured) == 1
    assert "login/oauth/access_token" in str(captured[0].url)
    body = captured[0].content.decode()
    assert "grant_type=authorization_code" in body
    assert "code=test-code" in body


async def test_auth_flow_missing_auth(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed(factory, provider="1password-scim", unique_key="1password-scim")

    async with _client(app) as client:
        response = await client.post(
            "/api-auth/api-key/1password-scim?connection_id=conn-test",
            json={"apiKey": "test-key"},
        )

    assert response.status_code == 401


async def test_auth_flow_unknown_provider_config(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await seed_full_auth(factory, scopes=["environment:*"])

    async with _client(app) as client:
        response = await client.post(
            "/api-auth/api-key/ghost?connection_id=conn-test",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={"apiKey": "test-key"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_provider_config"