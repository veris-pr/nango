"""End-to-end proxy route tests against a mock upstream.

Seeds the full auth stack + integration + connection, injects an httpx
MockTransport so the proxy route's upstream client calls the mock, and verifies
credential injection, response passthrough, retries, and error handling.
"""

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
from tests.integration._seeds_connections import seed_connection

BASE_PUBLIC_URL = "https://public.test"
GITHUB_PROXY = {"base_url": "https://api.github.com"}
_OAUTH2_CREDS: dict[str, object] = {"type": "OAUTH2", "access_token": "gho_token123"}
_API_KEY_CREDS: dict[str, object] = {"type": "API_KEY", "apiKey": "key-123"}
_BASIC_CREDS: dict[str, object] = {"type": "BASIC", "username": "user", "password": "pass"}


def _mock_transport(handler: Any) -> MockTransport:
    return MockTransport(handler)


def _make_app(
    factory: async_sessionmaker[AsyncSession],
    *,
    transport: Any = None,
) -> Any:
    return create_app(
        session_factory=factory,
        encryption_key=DEFAULT_KEY,
        base_public_url=BASE_PUBLIC_URL,
        webhook_receive_url="https://webhook.test",
        httpx_transport=transport,
    )


async def _seed_oauth2_world(
    factory: async_sessionmaker[AsyncSession],
    *,
    scopes: list[str] | None = None,
    creds: dict[str, object] | None = None,
    integration_key: str = "github",
    provider: str = "github",
) -> int:
    env_id, _ = await seed_full_auth(
        factory, scopes=scopes or ["environment:proxy"]
    )
    config_id = await seed_integration(
        factory, environment_id=env_id, unique_key=integration_key, provider=provider
    )
    await seed_connection(
        factory,
        environment_id=env_id,
        config_id=config_id,
        connection_id="conn-1",
        provider_config_key=integration_key,
        credentials=creds or _OAUTH2_CREDS,
        tags={},
    )
    return env_id


def _proxy_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {DEFAULT_TEST_KEY}",
        "provider-config-key": "github",
        "connection-id": "conn-1",
    }


@pytest.fixture
async def app_and_factory(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> tuple[Any, async_sessionmaker[AsyncSession]]:
    return _make_app(db_session_factory), db_session_factory


def _client(app: Any) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_proxy_oauth2_bearer_passthrough(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_oauth2_world(factory)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True, "data": [1, 2, 3]})

    app.state.httpx_transport = _mock_transport(handler)

    async with _client(app) as client:
        response = await client.get(
            "/proxy/repos/octocat/hello", headers=_proxy_headers()
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "data": [1, 2, 3]}
    assert len(captured) == 1
    assert captured[0].headers["authorization"] == "Bearer gho_token123"
    assert str(captured[0].url) == "https://api.github.com/repos/octocat/hello"


async def test_proxy_api_key_via_provider_headers(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    # Use the real catalog's 1password-scim which has
    # proxy.headers.authorization = "Bearer ${apiKey}".
    env_id, _ = await seed_full_auth(factory, scopes=["environment:proxy"])
    config_id = await seed_integration(
        factory, environment_id=env_id, unique_key="1password-scim", provider="1password-scim"
    )
    await seed_connection(
        factory,
        environment_id=env_id,
        config_id=config_id,
        connection_id="conn-1",
        provider_config_key="1password-scim",
        credentials=_API_KEY_CREDS,
        connection_config={"domain": "scim.example.com"},
        tags={},
    )
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"data": []})

    app.state.httpx_transport = _mock_transport(handler)

    headers = _proxy_headers()
    headers["provider-config-key"] = "1password-scim"
    async with _client(app) as client:
        response = await client.get("/proxy/Users", headers=headers)

    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0].headers["authorization"] == "Bearer key-123"


async def test_proxy_basic_auth(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_oauth2_world(factory, creds=_BASIC_CREDS)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, text="ok")

    app.state.httpx_transport = _mock_transport(handler)

    async with _client(app) as client:
        response = await client.get("/proxy/test", headers=_proxy_headers())

    assert response.status_code == 200
    import base64

    expected = base64.b64encode(b"user:pass").decode("ascii")
    assert captured[0].headers["authorization"] == f"Basic {expected}"


async def test_proxy_error_passthrough(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_oauth2_world(factory)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "Not found"})

    app.state.httpx_transport = _mock_transport(handler)

    async with _client(app) as client:
        response = await client.get("/proxy/missing", headers=_proxy_headers())

    assert response.status_code == 404
    assert response.json() == {"error": "Not found"}


async def test_proxy_retry_on_500(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_oauth2_world(factory)
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text="Internal Server Error")

    app.state.httpx_transport = _mock_transport(handler)

    headers = _proxy_headers()
    headers["retries"] = "2"
    async with _client(app) as client:
        response = await client.get("/proxy/test", headers=headers)

    assert response.status_code == 500
    assert call_count == 3  # 1 initial + 2 retries


async def test_proxy_retry_on_with_header(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_oauth2_world(factory)
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return httpx.Response(418, text="I'm a teapot")
        return httpx.Response(200, text="ok")

    app.state.httpx_transport = _mock_transport(handler)

    headers = _proxy_headers()
    headers["retries"] = "1"
    headers["retry-on"] = "418"
    async with _client(app) as client:
        response = await client.get("/proxy/test", headers=headers)

    assert response.status_code == 200
    assert call_count == 2


async def test_proxy_missing_auth(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_oauth2_world(factory)
    app.state.httpx_transport = _mock_transport(
        lambda req: httpx.Response(200, text="should not reach")
    )

    async with _client(app) as client:
        response = await client.get(
            "/proxy/test", headers={"provider-config-key": "github", "connection-id": "conn-1"}
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_auth_header"


async def test_proxy_missing_scope(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_oauth2_world(factory, scopes=["environment:integrations:read"])

    async with _client(app) as client:
        response = await client.get("/proxy/test", headers=_proxy_headers())

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert "environment:proxy" in response.json()["error"]["message"]


async def test_proxy_unknown_provider_config(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await seed_full_auth(factory, scopes=["environment:proxy"])

    headers = _proxy_headers()
    headers["provider-config-key"] = "ghost"
    async with _client(app) as client:
        response = await client.get("/proxy/test", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_provider_config"


async def test_proxy_missing_connection(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await seed_full_auth(factory, scopes=["environment:proxy"])
    await seed_integration(factory, environment_id=env_id, unique_key="github", provider="github")

    headers = _proxy_headers()
    headers["connection-id"] = "missing-conn"
    async with _client(app) as client:
        response = await client.get("/proxy/test", headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "server_error"
    assert "Failed to get connection" in response.json()["error"]["message"]


async def test_proxy_missing_required_headers(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_oauth2_world(factory)

    async with _client(app) as client:
        response = await client.get(
            "/proxy/test", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_headers"


async def test_proxy_post_body_passthrough(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_oauth2_world(factory)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(201, json={"created": True})

    app.state.httpx_transport = _mock_transport(handler)

    async with _client(app) as client:
        response = await client.post(
            "/proxy/repos",
            headers={**_proxy_headers(), "content-type": "application/json"},
            json={"name": "new-repo", "private": True},
        )

    assert response.status_code == 201
    assert response.json() == {"created": True}
    assert captured[0].method == "POST"
    body = captured[0].content
    assert b'"name"' in body and b'"new-repo"' in body