"""E2e tests for connect sessions.

POST /connect/sessions, GET /connect/session, DELETE /connect/session."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.server.app import create_app
from tests.integration._seeds import DEFAULT_KEY, DEFAULT_TEST_KEY, seed_full_auth

BASE_PUBLIC_URL = "https://public.test"
CONNECT_URL = "https://connect.test"


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


async def _seed_auth(
    factory: async_sessionmaker[AsyncSession],
    scopes: list[str] | None = None,
) -> int:
    env_id, _ = await seed_full_auth(
        factory, scopes=scopes or ["environment:connect_sessions:write"]
    )
    return env_id


async def test_create_connect_session_returns_token(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_auth(factory)

    async with _client(app) as client:
        response = await client.post(
            "/connect/sessions",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={
                "end_user": {"id": "eu-1", "email": "ada@example.com", "display_name": "Ada"},
                "organization": {"id": "org-1", "display_name": "Acme"},
            },
        )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["token"].startswith("nango_connect_session_")
    assert "connect_link" in data
    assert "expires_at" in data


async def test_create_with_tags_no_end_user(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_auth(factory)

    async with _client(app) as client:
        response = await client.post(
            "/connect/sessions",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={"tags": {"tenant": "alpha"}},
        )

    assert response.status_code == 201
    assert response.json()["data"]["token"].startswith("nango_connect_session_")


async def test_create_without_end_user_or_tags_rejected(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_auth(factory)

    async with _client(app) as client:
        response = await client.post(
            "/connect/sessions",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={},
        )

    assert response.status_code == 422


async def test_get_connect_session_returns_data(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_auth(factory)

    async with _client(app) as client:
        create_response = await client.post(
            "/connect/sessions",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={
                "end_user": {"id": "eu-1", "email": "ada@example.com", "display_name": "Ada"},
                "organization": {"id": "org-1", "display_name": "Acme"},
                "allowed_integrations": ["github"],
                "tags": {"team": "alpha"},
            },
        )
        token = create_response.json()["data"]["token"]

        get_response = await client.get(
            "/connect/session",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert get_response.status_code == 200
    data = get_response.json()["data"]
    assert data["endUser"] is not None
    assert data["endUser"]["id"] == "eu-1"
    assert data["allowed_integrations"] == ["github"]
    assert "isReconnecting" not in data or data["isReconnecting"] is False


async def test_get_connect_session_invalid_token_returns_not_found(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_auth(factory)

    async with _client(app) as client:
        response = await client.get(
            "/connect/session",
            headers={"Authorization": "Bearer nango_connect_session_nonexistent"},
        )

    assert response.status_code == 404


async def test_delete_connect_session(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_auth(factory)

    async with _client(app) as client:
        create_response = await client.post(
            "/connect/sessions",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={"tags": {"tenant": "alpha"}},
        )
        token = create_response.json()["data"]["token"]

        delete_response = await client.delete(
            "/connect/session",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Confirm deleted — GET should now fail
        get_response = await client.get(
            "/connect/session",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


async def test_create_missing_auth(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_auth(factory)

    async with _client(app) as client:
        response = await client.post(
            "/connect/sessions",
            json={"tags": {"tenant": "alpha"}},
        )

    assert response.status_code == 401


async def test_create_missing_scope(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_auth(factory, scopes=["environment:integrations:read"])

    async with _client(app) as client:
        response = await client.post(
            "/connect/sessions",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={"tags": {"tenant": "alpha"}},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"