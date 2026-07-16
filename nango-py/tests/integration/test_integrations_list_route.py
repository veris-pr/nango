"""End-to-end route test: GET /integrations (list) with api-key auth.

Connect-session auth and its ``allowed_integrations`` filter are a deferred
follow-up; the api-key path returns every integration config for the
authenticated environment.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.server.app import create_app
from tests.integration._seeds import (
    DEFAULT_KEY,
    DEFAULT_TEST_KEY,
    seed_account,
    seed_environment,
    seed_full_auth,
    seed_integration,
)

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


async def test_list_returns_all_integrations_ordered_by_provider(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await seed_full_auth(factory, scopes=["environment:integrations:list"])
    await seed_integration(
        factory,
        environment_id=env_id,
        unique_key="slack-prod",
        provider="slack",
        display_name="Slack",
    )
    await seed_integration(
        factory,
        environment_id=env_id,
        unique_key="github-prod",
        provider="github",
        display_name="GitHub",
    )

    async with _client(app) as client:
        response = await client.get(
            "/integrations", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert [item["provider"] for item in data] == ["github", "slack"]  # ordered by provider ASC
    github = next(item for item in data if item["provider"] == "github")
    assert set(github.keys()) == {
        "unique_key",
        "provider",
        "display_name",
        "logo",
        "forward_webhooks",
        "created_at",
        "updated_at",
    }
    assert github["unique_key"] == "github-prod"
    assert github["display_name"] == "GitHub"
    assert github["logo"] == f"{BASE_PUBLIC_URL}/images/template-logos/github.svg"


async def test_list_authorized_with_list_credentials_scope(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await seed_full_auth(
        factory, scopes=["environment:integrations:list_credentials"]
    )
    await seed_integration(factory, environment_id=env_id, unique_key="github", provider="github")

    async with _client(app) as client:
        response = await client.get(
            "/integrations", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 200


async def test_list_forbidden_without_matching_scope(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await seed_full_auth(factory, scopes=["environment:connections:read"])
    await seed_integration(factory, environment_id=env_id, unique_key="github", provider="github")

    async with _client(app) as client:
        response = await client.get(
            "/integrations", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_list_rejects_query_params(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await seed_full_auth(factory, scopes=["environment:integrations:list"])

    async with _client(app) as client:
        response = await client.get(
            "/integrations?foo=bar", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_query_params"


async def test_list_empty_when_no_integrations(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await seed_full_auth(factory, scopes=["environment:integrations:list"])

    async with _client(app) as client:
        response = await client.get(
            "/integrations", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_list_requires_auth(app_and_factory: tuple[Any, Any]) -> None:
    app, _ = app_and_factory
    async with _client(app) as client:
        response = await client.get("/integrations")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_auth_header"


async def test_list_excludes_deleted_integrations(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await seed_full_auth(factory, scopes=["environment:integrations:list"])
    await seed_integration(factory, environment_id=env_id, unique_key="github", provider="github")
    await seed_integration(
        factory, environment_id=env_id, unique_key="deleted-one", provider="zoom", deleted=True
    )

    async with _client(app) as client:
        response = await client.get(
            "/integrations", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 200
    providers = [item["provider"] for item in response.json()["data"]]
    assert providers == ["github"]
    assert "zoom" not in providers


async def test_list_scoped_to_authenticated_environment(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await seed_full_auth(factory, scopes=["environment:integrations:list"])
    await seed_integration(factory, environment_id=env_id, unique_key="github", provider="github")
    # A second environment with its own integration must not appear.
    other_account = await seed_account(factory, name="other-team")
    other_env, _ = await seed_environment(factory, other_account, name="prod")
    await seed_integration(
        factory, environment_id=other_env, unique_key="other-env", provider="slack"
    )

    async with _client(app) as client:
        response = await client.get(
            "/integrations", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 200
    providers = [item["provider"] for item in response.json()["data"]]
    assert providers == ["github"]
    assert "slack" not in providers