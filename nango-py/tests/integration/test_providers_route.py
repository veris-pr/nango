"""End-to-end route tests: GET /providers and GET /providers/:provider.

The provider routes read the global catalog (no environment scoping in the
response) but still require authentication. apiAuth covers the node-client
path; connect-session auth (Connect UI) is a deferred follow-up.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.server.app import create_app
from tests.integration._seeds import DEFAULT_KEY, DEFAULT_TEST_KEY, seed_full_auth

BASE_PUBLIC_URL = "https://public.test"


@pytest.fixture
async def app_and_factory(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> tuple[Any, async_sessionmaker[AsyncSession]]:
    app = create_app(
        session_factory=db_session_factory,
        encryption_key=DEFAULT_KEY,
        base_public_url=BASE_PUBLIC_URL,
        webhook_receive_url="https://webhook.test",
    )
    return app, db_session_factory


def _client(app: Any) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _authed(app: Any, factory: async_sessionmaker[AsyncSession]) -> AsyncClient:
    await seed_full_auth(factory, scopes=["environment:integrations:read"])
    return _client(app)


async def test_list_providers_returns_catalog(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    async with await _authed(app, factory) as client:
        response = await client.get(
            "/providers", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)
    assert len(data) > 700  # providers.yaml catalogs hundreds of providers
    github = next(p for p in data if p["name"] == "github")
    assert github["auth_mode"] == "OAUTH2"
    assert github["logo_url"] == f"{BASE_PUBLIC_URL}/images/template-logos/github.svg"


async def test_list_providers_with_search_filters(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    async with await _authed(app, factory) as client:
        response = await client.get(
            "/providers?search=github",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert response.status_code == 200
    names = [p["name"] for p in response.json()["data"]]
    assert all("github" in name.lower() for name in names)
    assert "github" in names


async def test_get_provider_returns_single_entry(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    async with await _authed(app, factory) as client:
        response = await client.get(
            "/providers/github", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "github"
    assert data["auth_mode"] == "OAUTH2"
    assert data["logo_url"] == f"{BASE_PUBLIC_URL}/images/template-logos/github.svg"


async def test_get_provider_unknown_returns_not_found(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    async with await _authed(app, factory) as client:
        response = await client.get(
            "/providers/ghost", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Unknown provider ghost"}}


async def test_get_provider_rejects_query_params(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    async with await _authed(app, factory) as client:
        response = await client.get(
            "/providers/github?foo=bar",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_query_params"


async def test_get_provider_invalid_name_returns_invalid_uri_params(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    async with await _authed(app, factory) as client:
        response = await client.get(
            "/providers/bad!name", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_uri_params"


async def test_list_providers_rejects_unknown_query(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    async with await _authed(app, factory) as client:
        response = await client.get(
            "/providers?foo=bar",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_query_params"


async def test_providers_require_auth(app_and_factory: tuple[Any, Any]) -> None:
    app, _ = app_and_factory
    async with _client(app) as client:
        response = await client.get("/providers")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_auth_header"