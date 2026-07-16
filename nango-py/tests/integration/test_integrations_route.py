"""End-to-end route test: GET /integrations/:uniqueKey through the real app.

Seeds the migrated schema, builds the FastAPI app wired to the real SQLAlchemy
auth gateway, integration repository, and provider catalog, then drives the
route via ASGI and asserts the TypeScript-compatible response envelopes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.server.app import create_app
from tests.integration._seeds import (
    DEFAULT_KEY,
    seed_account,
    seed_api_secret,
    seed_customer_key,
    seed_environment,
    seed_integration,
)

BASE_PUBLIC_URL = "https://public.test"
WEBHOOK_RECEIVE_URL = "https://webhook.test"
GITHUB_KEY = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
async def app_and_factory(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> tuple[Any, async_sessionmaker[AsyncSession]]:
    app = create_app(
        session_factory=db_session_factory,
        encryption_key=DEFAULT_KEY,
        base_public_url=BASE_PUBLIC_URL,
        webhook_receive_url=WEBHOOK_RECEIVE_URL,
    )
    return app, db_session_factory


async def _seed_full_auth(
    factory: async_sessionmaker[AsyncSession],
    *,
    scopes: list[str],
    plaintext: str = GITHUB_KEY,
) -> tuple[int, str]:
    account_id = await seed_account(factory)
    env_id, env_uuid = await seed_environment(factory, account_id)
    await seed_api_secret(factory, environment_id=env_id, plaintext="default-plain")
    await seed_customer_key(
        factory,
        account_id=account_id,
        environment_id=env_id,
        plaintext=plaintext,
        scopes=scopes,
    )
    return env_id, env_uuid


def _client(app: Any) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_success_no_include(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await _seed_full_auth(factory, scopes=["environment:integrations:read"])
    await seed_integration(
        factory,
        environment_id=env_id,
        unique_key="github",
        provider="github",
        display_name="GitHub",
    )

    async with _client(app) as client:
        response = await client.get(
            "/integrations/github", headers={"Authorization": f"Bearer {GITHUB_KEY}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert set(body["data"].keys()) == {
        "unique_key",
        "provider",
        "display_name",
        "logo",
        "forward_webhooks",
        "created_at",
        "updated_at",
    }
    assert body["data"]["unique_key"] == "github"
    assert body["data"]["provider"] == "github"
    assert body["data"]["display_name"] == "GitHub"
    assert body["data"]["logo"] == f"{BASE_PUBLIC_URL}/images/template-logos/github.svg"
    assert body["data"]["forward_webhooks"] is True


async def test_success_credentials_include(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await _seed_full_auth(factory, scopes=["environment:integrations:read_credentials"])
    await seed_integration(
        factory,
        environment_id=env_id,
        unique_key="github",
        provider="github",
        custom={"webhookSecret": "wh-secret-abc"},
    )

    async with _client(app) as client:
        response = await client.get(
            "/integrations/github?include=credentials",
            headers={"Authorization": f"Bearer {GITHUB_KEY}"},
        )

    assert response.status_code == 200
    creds = response.json()["data"]["credentials"]
    assert creds == {
        "type": "OAUTH2",
        "client_id": "client-123",
        "client_secret": "secret-456",
        "scopes": "repo,user",
        "webhook_secret": "wh-secret-abc",
    }


async def test_success_webhook_include(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, env_uuid = await _seed_full_auth(factory, scopes=["environment:integrations:read"])
    await seed_integration(
        factory,
        environment_id=env_id,
        unique_key="airtable",
        provider="airtable",  # providers.yaml: airtable has webhook_routing_script
        display_name="Airtable",
    )

    async with _client(app) as client:
        response = await client.get(
            "/integrations/airtable?include=webhook",
            headers={"Authorization": f"Bearer {GITHUB_KEY}"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["webhook_url"] == (
        f"{WEBHOOK_RECEIVE_URL}/{env_uuid}/airtable"
    )


async def test_credentials_omitted_when_read_scope_only(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await _seed_full_auth(factory, scopes=["environment:integrations:read"])
    await seed_integration(factory, environment_id=env_id, unique_key="github", provider="github")

    async with _client(app) as client:
        response = await client.get(
            "/integrations/github?include=credentials",
            headers={"Authorization": f"Bearer {GITHUB_KEY}"},
        )

    assert response.status_code == 200
    assert "credentials" not in response.json()["data"]


async def test_missing_auth(app_and_factory: tuple[Any, Any]) -> None:
    app, _ = app_and_factory
    async with _client(app) as client:
        response = await client.get("/integrations/github")
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "message": "Authentication failed. The request is missing the Authorization header.",
            "code": "missing_auth_header",
            "payload": {},
        }
    }


async def test_malformed_auth(app_and_factory: tuple[Any, Any]) -> None:
    app, _ = app_and_factory
    async with _client(app) as client:
        response = await client.get(
            "/integrations/github", headers={"Authorization": "Bearer "}
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "malformed_auth_header"


async def test_invalid_secret_key_format(app_and_factory: tuple[Any, Any]) -> None:
    app, _ = app_and_factory
    async with _client(app) as client:
        response = await client.get(
            "/integrations/github", headers={"Authorization": "Bearer not-a-uuid"}
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_secret_key_format"


async def test_unknown_account(app_and_factory: tuple[Any, Any]) -> None:
    app, _ = app_and_factory
    async with _client(app) as client:
        response = await client.get(
            "/integrations/github",
            headers={"Authorization": "Bearer 00000000-0000-4000-8000-000000000000"},
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unknown_account"


async def test_unknown_integration(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_full_auth(factory, scopes=["environment:integrations:read"])

    async with _client(app) as client:
        response = await client.get(
            "/integrations/ghost", headers={"Authorization": f"Bearer {GITHUB_KEY}"}
        )

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": 'Integration "ghost" does not exist'}
    }


async def test_missing_scope(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await _seed_full_auth(factory, scopes=["environment:connections:read"])
    await seed_integration(factory, environment_id=env_id, unique_key="github", provider="github")

    async with _client(app) as client:
        response = await client.get(
            "/integrations/github", headers={"Authorization": f"Bearer {GITHUB_KEY}"}
        )

    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "forbidden"
    assert "environment:integrations:read" in body["message"]


async def test_invalid_query_params(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_full_auth(factory, scopes=["environment:integrations:read"])
    await seed_integration(factory, environment_id=1, unique_key="github", provider="github")

    async with _client(app) as client:
        response = await client.get(
            "/integrations/github?include=bogus",
            headers={"Authorization": f"Bearer {GITHUB_KEY}"},
        )

    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] == "invalid_query_params"
    assert body["errors"][0]["path"] == ["include"]


async def test_created_at_serializes_with_z_suffix(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await _seed_full_auth(factory, scopes=["environment:integrations:read"])
    await seed_integration(factory, environment_id=env_id, unique_key="github", provider="github")

    async with _client(app) as client:
        response = await client.get(
            "/integrations/github", headers={"Authorization": f"Bearer {GITHUB_KEY}"}
        )

    created_at = response.json()["data"]["created_at"]
    assert created_at.endswith("Z")
    # Sanity: parses back to a timezone-aware datetime.
    parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.tzinfo.utcoffset(parsed) == UTC.utcoffset(parsed)