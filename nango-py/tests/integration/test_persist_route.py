"""E2e tests for persist routes: records CRUD, checkpoints, auth."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.server.app import create_app
from tests.integration._seeds import DEFAULT_KEY, DEFAULT_TEST_KEY, seed_full_auth, seed_integration
from tests.integration._seeds_connections import seed_connection

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


_SYNC_ID = "00000000-0000-4000-8000-000000000001"
_RECORDS_PATH = "/environment/{eid}/connection/{cid}/sync/" + _SYNC_ID + "/job/1/records"
_CHECKPOINT_PATH = "/environment/{eid}/connection/{cid}/checkpoint"


async def _seed(
    factory: async_sessionmaker[AsyncSession],
    *,
    connection_id: int = 0,
) -> int:
    env_id, _ = await seed_full_auth(factory, scopes=["environment:*"])
    if connection_id:
        config_id = await seed_integration(
            factory, environment_id=env_id, unique_key="test-int", provider="github"
        )
        await seed_connection(
            factory, environment_id=env_id, config_id=config_id,
            connection_id=f"conn-{connection_id}", provider_config_key="test-int",
            credentials={"type": "OAUTH2", "access_token": "tok"}, tags={},
        )
    return env_id


async def test_post_records_saves_and_returns_count(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id = await _seed(factory)

    async with _client(app) as client:
        response = await client.post(
            _RECORDS_PATH.format(eid=env_id, cid=10),
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={
                "model": "Contact",
                "records": [
                    {"id": "ext-1", "data": {"name": "Ada"}, "metadata": {"source": "test"}},
                    {"id": "ext-2", "data": {"name": "Grace"}, "metadata": {}},
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["records"] == 2


async def test_get_records_lists_with_pagination(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id = await _seed(factory)

    async with _client(app) as client:
        await client.post(
            _RECORDS_PATH.format(eid=env_id, cid=20),
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={
                "model": "Account",
                "records": [
                    {"id": "a-1", "data": {"name": "Acme"}, "metadata": {}},
                    {"id": "a-2", "data": {"name": "Globex"}, "metadata": {}},
                ],
            },
        )
        response = await client.get(
            f"/environment/{env_id}/connection/20/records?model=Account&limit=1",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["records"]) == 1
    assert body["next_cursor"] is not None
    assert body["records"][0]["external_id"] in ("a-1", "a-2")


async def test_put_records_merges_existing_data(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id = await _seed(factory)

    async with _client(app) as client:
        await client.post(
            _RECORDS_PATH.format(eid=env_id, cid=30),
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={
                "model": "Lead",
                "records": [{"id": "l-1", "data": {"name": "Ada", "score": 10}, "metadata": {}}],
            },
        )
        await client.put(
            _RECORDS_PATH.format(eid=env_id, cid=30),
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={
                "model": "Lead",
                "records": [{"id": "l-1", "data": {"score": 99}, "metadata": {}}],
            },
        )
        response = await client.get(
            f"/environment/{env_id}/connection/30/records?model=Lead",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    body = response.json()
    assert body["records"][0]["data"]["name"] == "Ada"
    assert body["records"][0]["data"]["score"] == 99


async def test_delete_records_soft_deletes(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id = await _seed(factory)

    async with _client(app) as client:
        await client.post(
            _RECORDS_PATH.format(eid=env_id, cid=40),
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={
                "model": "Task",
                "records": [{"id": "t-1", "data": {"title": "Done"}, "metadata": {}}],
            },
        )
        del_resp = await client.request(
            "DELETE",
            _RECORDS_PATH.format(eid=env_id, cid=40),
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={"model": "Task", "externalIds": ["t-1"]},
        )
        get_all = await client.get(
            f"/environment/{env_id}/connection/40/records?model=Task&includeDeleted=false",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] == 1
    assert len(get_all.json()["records"]) == 0


async def test_put_and_get_checkpoint(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id = await _seed(factory, connection_id=50)
    # Get the actual connection DB id for the checkpoint FK
    from sqlalchemy import text
    async with factory() as s:
        row = (await s.execute(
            text("SELECT id FROM _nango_connections WHERE connection_id = 'conn-50' LIMIT 1"),
        )).scalar()
    actual_cid = int(row) if row else 50

    async with _client(app) as client:
        put_resp = await client.put(
            _CHECKPOINT_PATH.format(eid=env_id, cid=actual_cid),
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={"model": "Contact", "key": "sync", "cursor": "cursor-abc"},
        )
        get_resp = await client.get(
            f"{_CHECKPOINT_PATH.format(eid=env_id, cid=actual_cid)}?model=Contact&key=sync",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert put_resp.status_code == 200
    assert get_resp.status_code == 200
    assert get_resp.json()["checkpoint"]["cursor"] == "cursor-abc"


async def test_get_checkpoint_not_found(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id = await _seed(factory)

    async with _client(app) as client:
        response = await client.get(
            f"{_CHECKPOINT_PATH.format(eid=env_id, cid=60)}?model=X&key=missing",
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
        )

    assert response.status_code == 404


async def test_persist_env_mismatch_rejected(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    await _seed(factory)

    async with _client(app) as client:
        response = await client.post(
            _RECORDS_PATH.format(eid=999, cid=10),
            headers={"Authorization": f"Bearer {DEFAULT_TEST_KEY}"},
            json={"model": "X", "records": [{"id": "1", "data": {}, "metadata": {}}]},
        )

    assert response.status_code == 401


async def test_persist_missing_auth(
    app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
) -> None:
    app, factory = app_and_factory
    env_id = await _seed(factory)

    async with _client(app) as client:
        response = await client.post(
            _RECORDS_PATH.format(eid=env_id, cid=10),
            json={"model": "X", "records": [{"id": "1", "data": {}, "metadata": {}}]},
        )

    assert response.status_code == 401