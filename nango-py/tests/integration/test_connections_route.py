"""End-to-end route tests: GET /connections (list) and GET /connections/:id.

Seeds end_users, _nango_connections (with encrypted credentials), and
_nango_active_logs, then drives the routes via ASGI and asserts the
TypeScript-compatible envelopes. Credential refresh is deferred; the read path
returns stored decrypted credentials.
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
    seed_full_auth,
    seed_integration,
)
from tests.integration._seeds_connections import (
    seed_active_log,
    seed_connection,
    seed_end_user,
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


_OAUTH2_CREDS: dict[str, object] = {
    "type": "OAUTH2",
    "access_token": "access-abc",
    "refresh_token": "refresh-xyz",
    "raw": {"refresh_token": "refresh-xyz", "extra": "keep"},
}


async def _gh_integration(
    factory: async_sessionmaker[AsyncSession], env_id: int
) -> int:
    return await seed_integration(
        factory, environment_id=env_id, unique_key="github", provider="github"
    )


async def _seed_world(
    factory: async_sessionmaker[AsyncSession],
    *,
    scopes: list[str],
    connection_id: str = "conn-1",
    end_user: bool = True,
    active_log: bool = True,
    creds: dict[str, object] | None = None,
    tags: dict[str, str] | None = None,
    deleted: bool = False,
) -> int:
    env_id, _ = await seed_full_auth(factory, scopes=scopes)
    config_id = await _gh_integration(factory, env_id)
    end_user_id: int | None = None
    if end_user:
        end_user_id = await seed_end_user(
            factory,
            account_id=1,
            environment_id=env_id,
            end_user_id="eu-1",
            email="ada@example.com",
            display_name="Ada Lovelace",
            organization_id="org-1",
            organization_display_name="Acme",
        )
    conn_id = await seed_connection(
        factory,
        environment_id=env_id,
        config_id=config_id,
        connection_id=connection_id,
        provider_config_key="github",
        credentials=creds or _OAUTH2_CREDS,
        end_user_id=end_user_id,
        tags=tags or {"team": "alpha"},
        metadata={"region": "us"},
        connection_config={"oauth_scopes_override": ["repo"]},
        deleted=deleted,
    )
    if active_log:
        await seed_active_log(factory, connection_id=conn_id, type_value="auth", log_id="log-9")
    return env_id


async def test_list_returns_connections_with_end_user_and_errors(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_world(factory, scopes=["environment:connections:list"])

    async with _client(app) as client:
        response = await client.get(
            "/connections", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 200
    item = response.json()["connections"][0]
    assert set(item.keys()) == {
        "id",
        "connection_id",
        "provider_config_key",
        "provider",
        "errors",
        "end_user",
        "tags",
        "metadata",
        "created",
    }
    assert item["connection_id"] == "conn-1"
    assert item["provider"] == "github"
    assert item["errors"] == [{"type": "auth", "log_id": "log-9"}]
    assert item["end_user"] == {
        "id": "eu-1",
        "display_name": "Ada Lovelace",
        "email": "ada@example.com",
        "tags": None,
        "organization": {"id": "org-1", "display_name": "Acme"},
    }
    assert item["tags"] == {"team": "alpha"}
    assert item["metadata"] == {"region": "us"}
    assert "credentials" not in item


async def test_list_filtered_by_search(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await seed_full_auth(factory, scopes=["environment:connections:list"])
    config_id = await _gh_integration(factory, env_id)
    eu = await seed_end_user(
        factory,
        account_id=1,
        environment_id=env_id,
        end_user_id="eu-1",
        display_name="Ada Lovelace",
    )
    await seed_connection(
        factory, environment_id=env_id, config_id=config_id, connection_id="conn-1",
        provider_config_key="github", credentials=_OAUTH2_CREDS, end_user_id=eu, tags={},
    )
    await seed_connection(
        factory, environment_id=env_id, config_id=config_id, connection_id="conn-2",
        provider_config_key="github", credentials=_OAUTH2_CREDS, tags={},
    )

    async with _client(app) as client:
        response = await client.get(
            "/connections?search=ada",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    ids = [item["connection_id"] for item in response.json()["connections"]]
    assert ids == ["conn-1"]


async def test_list_filtered_by_tags(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await seed_full_auth(factory, scopes=["environment:connections:list"])
    config_id = await _gh_integration(factory, env_id)
    await seed_connection(
        factory, environment_id=env_id, config_id=config_id, connection_id="conn-1",
        provider_config_key="github", credentials=_OAUTH2_CREDS, tags={"team": "alpha"},
    )
    await seed_connection(
        factory, environment_id=env_id, config_id=config_id, connection_id="conn-2",
        provider_config_key="github", credentials=_OAUTH2_CREDS, tags={"team": "beta"},
    )

    async with _client(app) as client:
        response = await client.get(
            "/connections?tags[team]=alpha",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    ids = [item["connection_id"] for item in response.json()["connections"]]
    assert ids == ["conn-1"]


async def test_list_excludes_deleted(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await seed_full_auth(factory, scopes=["environment:connections:list"])
    config_id = await _gh_integration(factory, env_id)
    await seed_connection(
        factory, environment_id=env_id, config_id=config_id, connection_id="conn-1",
        provider_config_key="github", credentials=_OAUTH2_CREDS, tags={},
    )
    await seed_connection(
        factory, environment_id=env_id, config_id=config_id, connection_id="conn-del",
        provider_config_key="github", credentials=_OAUTH2_CREDS, tags={}, deleted=True,
    )

    async with _client(app) as client:
        response = await client.get(
            "/connections", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    ids = [item["connection_id"] for item in response.json()["connections"]]
    assert ids == ["conn-1"]


async def test_list_missing_scope(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_world(factory, scopes=["environment:integrations:read"])

    async with _client(app) as client:
        response = await client.get(
            "/connections", headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"}
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_list_requires_auth(app_and_factory: tuple[Any, Any]) -> None:
    app, _ = app_and_factory
    async with _client(app) as client:
        response = await client.get("/connections")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_auth_header"


async def test_single_no_credentials_scope_returns_empty_credentials(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_world(factory, scopes=["environment:connections:read"])

    async with _client(app) as client:
        response = await client.get(
            "/connections/conn-1?provider_config_key=github",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["connection_id"] == "conn-1"
    assert body["credentials"] == {}
    assert body["connection_config"] == {"oauth_scopes_override": ["repo"]}
    assert body["end_user"]["organization"] == {"id": "org-1", "display_name": "Acme"}


async def test_single_with_credentials_strips_refresh_token(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_world(factory, scopes=["environment:connections:read_credentials"])

    async with _client(app) as client:
        response = await client.get(
            "/connections/conn-1?provider_config_key=github&refresh_token=false",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert response.status_code == 200
    creds = response.json()["credentials"]
    assert creds["type"] == "OAUTH2"
    assert creds["access_token"] == "access-abc"
    assert "refresh_token" not in creds
    assert creds["raw"] == {"extra": "keep"}


async def test_single_with_credentials_keeps_refresh_token_when_requested(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed_world(factory, scopes=["environment:connections:read_credentials"])

    async with _client(app) as client:
        response = await client.get(
            "/connections/conn-1?provider_config_key=github&refresh_token=true",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert response.status_code == 200
    assert response.json()["credentials"]["refresh_token"] == "refresh-xyz"


async def test_single_unknown_provider_config(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await seed_full_auth(factory, scopes=["environment:connections:read"])

    async with _client(app) as client:
        response = await client.get(
            "/connections/conn-1?provider_config_key=ghost",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "unknown_provider_config", "message": "Provider does not exists"}
    }


async def test_single_not_found(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id, _ = await seed_full_auth(factory, scopes=["environment:connections:read"])
    await _gh_integration(factory, env_id)

    async with _client(app) as client:
        response = await client.get(
            "/connections/missing-conn?provider_config_key=github",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Failed to find connection"}
    }


async def test_single_missing_provider_config_key(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await seed_full_auth(factory, scopes=["environment:connections:read"])

    async with _client(app) as client:
        response = await client.get(
            "/connections/conn-1",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_query_params"