from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from nango.persist import PersistService
from nango.persist.models import (
    CheckpointRequest,
    DeleteRecordsRequest,
    PersistAuthContext,
    PersistRecordsRequest,
)
from nango.server.app import create_app
from nango.server.settings import Settings

AUTH_HEADER = {"Authorization": "Bearer test-secret"}


def test_service_writes_lists_and_deletes_records() -> None:
    service = PersistService()
    auth = PersistAuthContext(environment_id=1, token="test-secret")

    service.persist_records(
        connection_id=10,
        sync_id="sync-1",
        sync_job_id=20,
        request=PersistRecordsRequest.model_validate(
            {
                "model": "Contact",
                "records": [{"id": "contact-1", "data": {"name": "Ada"}}],
                "activityLogId": "activity-1",
            }
        ),
        auth=auth,
        mode="save",
    )
    listed = service.list_records(
        connection_id=10,
        model="Contact",
        limit=100,
        cursor=None,
        include_deleted=False,
    )
    deleted = service.delete_records(
        connection_id=10,
        request=DeleteRecordsRequest.model_validate(
            {"model": "Contact", "externalIds": ["contact-1"]}
        ),
        auth=auth,
    )
    after_delete = service.list_records(
        connection_id=10,
        model="Contact",
        limit=100,
        cursor=None,
        include_deleted=False,
    )

    assert [record.external_id for record in listed.records] == ["contact-1"]
    assert deleted.deleted == 1
    assert after_delete.records == []


def test_service_checkpoint_flow_and_daemon_placeholders() -> None:
    service = PersistService()

    checkpoint = service.save_checkpoint(
        connection_id=10,
        request=CheckpointRequest(model="Contact", key="sync", cursor="cursor-1"),
    )
    loaded = service.get_checkpoint(connection_id=10, model="Contact", key="sync")

    assert loaded == checkpoint
    assert service.prune_records().status == "noop"
    assert service.delete_expired_records().status == "noop"


async def test_auth_placeholder_requires_bearer_token() -> None:
    app = create_app(Settings(service_name="test-core"))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get("/persist/v1/environment/1/connection/10/records?model=Contact")
        malformed = await client.get(
            "/persist/v1/environment/1/connection/10/records?model=Contact",
            headers={"Authorization": "Basic test-secret"},
        )

    assert missing.status_code == 401
    assert malformed.status_code == 401


async def test_persist_routes_write_list_delete_checkpoint_and_log() -> None:
    app = create_app(Settings(service_name="test-core"))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        written = await client.post(
            "/persist/v1/environment/1/connection/10/sync/sync-1/job/20/records",
            headers=AUTH_HEADER,
            json={
                "model": "Contact",
                "records": [
                    {
                        "id": "contact-1",
                        "data": {"name": "Ada"},
                        "metadata": {"source": "test"},
                    }
                ],
                "activityLogId": "activity-1",
            },
        )
        listed = await client.get(
            "/persist/v1/environment/1/connection/10/records",
            headers=AUTH_HEADER,
            params={"model": "Contact", "includeDeleted": False},
        )
        checkpoint_saved = await client.put(
            "/persist/v1/environment/1/connection/10/checkpoint",
            headers=AUTH_HEADER,
            json={"model": "Contact", "key": "sync", "cursor": "cursor-1"},
        )
        checkpoint_loaded = await client.get(
            "/persist/v1/environment/1/connection/10/checkpoint",
            headers=AUTH_HEADER,
            params={"model": "Contact", "key": "sync"},
        )
        logged = await client.post(
            "/persist/v1/environment/1/log",
            headers=AUTH_HEADER,
            json={
                "activityLogId": "activity-1",
                "message": "persisted",
                "createdAt": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC).isoformat(),
            },
        )
        deleted = await client.request(
            "DELETE",
            "/persist/v1/environment/1/connection/10/sync/sync-1/job/20/records",
            headers=AUTH_HEADER,
            json={"model": "Contact", "externalIds": ["contact-1"]},
        )
        pruned = await client.post("/persist/v1/daemon/prune")

    assert written.status_code == 200
    assert written.json()["records"] == 1
    assert listed.status_code == 200
    assert listed.json()["records"][0]["external_id"] == "contact-1"
    assert checkpoint_saved.status_code == 200
    assert checkpoint_loaded.json()["checkpoint"]["cursor"] == "cursor-1"
    assert logged.status_code == 204
    assert deleted.json() == {"deleted": 1}
    assert pruned.json() == {"status": "noop"}
