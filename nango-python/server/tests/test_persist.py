from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from nango.auth.models import (
    AccountContext,
    AccountSummary,
    EnvironmentSummary,
    SecretSummary,
)
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


async def test_service_writes_lists_and_deletes_records() -> None:
    service = PersistService()
    auth = PersistAuthContext(environment_id=1, token="test-secret")

    await service.persist_records(
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
    listed = await service.list_records(
        connection_id=10,
        model="Contact",
        limit=100,
        cursor=None,
        include_deleted=False,
    )
    deleted = await service.delete_records(
        connection_id=10,
        request=DeleteRecordsRequest.model_validate(
            {"model": "Contact", "externalIds": ["contact-1"]}
        ),
        auth=auth,
    )
    after_delete = await service.list_records(
        connection_id=10,
        model="Contact",
        limit=100,
        cursor=None,
        include_deleted=False,
    )

    assert [record.external_id for record in listed.records] == ["contact-1"]
    assert deleted.deleted == 1
    assert after_delete.records == []


async def test_service_checkpoint_flow_and_daemon_placeholders() -> None:
    service = PersistService()
    auth = PersistAuthContext(environment_id=1, token="test-secret")

    checkpoint = await service.save_checkpoint(
        connection_id=10,
        request=CheckpointRequest(model="Contact", key="sync", cursor="cursor-1"),
        auth=auth,
    )
    loaded = await service.get_checkpoint(
        connection_id=10,
        model="Contact",
        key="sync",
        auth=auth,
    )

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


async def test_persist_auth_rejects_mismatched_environment_when_resolved() -> None:
    class FakeAuthService:
        async def get_account_context_by_api_key(
            self,
            *,
            secret_key: str | None = None,
            internal_secret_key: str | None = None,
        ) -> AccountContext:
            del secret_key, internal_secret_key

            return AccountContext(
                account=AccountSummary(
                    id=1,
                    createdAt=datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                    updatedAt=datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                ),
                environment=EnvironmentSummary(
                    id=2,
                    name="dev",
                    accountId=1,
                    secretKey="test-secret",
                    isProduction=False,
                    createdAt=datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                    updatedAt=datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                ),
                secret=SecretSummary(
                    id=3,
                    environmentId=2,
                    displayName="default",
                    secret="test-secret",
                    hashed="hashed",
                    isDefault=True,
                    createdAt=datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                    updatedAt=datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                ),
                authSource="api_secret",
            )

    app = create_app(Settings(service_name="test-core"))
    async with app.router.lifespan_context(app):
        app.state.auth_service = FakeAuthService()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/persist/v1/environment/1/connection/10/records",
                headers=AUTH_HEADER,
                params={"model": "Contact"},
            )

    assert response.status_code == 401
    assert response.json() == {
        "detail": {
            "error": {
                "code": "unauthorized",
                "message": "Unauthorized: Matching environment not found",
            }
        }
    }


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


async def test_persist_routes_use_db_backed_repository_when_configured() -> None:
    pytest.importorskip("sqlalchemy")

    class FakeEngine:
        async def dispose(self) -> None:
            return None

    class FakeResult:
        def __init__(
            self,
            *,
            rows: list[dict[str, object]] | None = None,
            row: dict[str, object] | None = None,
        ) -> None:
            self._rows = rows or ([] if row is None else [row])

        def mappings(self) -> FakeResult:
            return self

        def all(self) -> list[dict[str, object]]:
            return self._rows

        def first(self) -> dict[str, object] | None:
            return self._rows[0] if self._rows else None

    class FakeSession:
        def __init__(self) -> None:
            self.records = [
                {
                    "id": "record-1",
                    "external_id": "contact-1",
                    "connection_id": 10,
                    "model": "Contact",
                    "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                    "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                    "deleted_at": None,
                    "sync_id": "sync-1",
                    "sync_job_id": 20,
                    "record_data": {"name": "Ada"},
                    "metadata_json": {"source": "test"},
                }
            ]
            self.checkpoint = {
                "checkpoint": {"cursor": "cursor-1"},
                "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
            }

        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def execute(self, query: object, params: dict[str, object]) -> FakeResult:
            query_text = str(query)
            if "FROM records AS r" in query_text and "LIMIT :limit" in query_text:
                return FakeResult(rows=self.records)
            if query_text.strip().startswith("INSERT INTO checkpoints"):
                return FakeResult(row=self.checkpoint)
            if "FROM checkpoints" in query_text:
                return FakeResult(row=self.checkpoint)
            if query_text.strip().startswith("UPDATE records"):
                return FakeResult(rows=[{"id": "record-1"}])
            if query_text.strip().startswith("INSERT INTO records_data"):
                return FakeResult()
            if query_text.strip().startswith("INSERT INTO records"):
                return FakeResult()
            return FakeResult()

        async def commit(self) -> None:
            return None

    class FakeSessionFactory:
        def __call__(self) -> FakeSession:
            return FakeSession()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("nango.server.app.create_engine", lambda _settings: FakeEngine())
    monkeypatch.setattr(
        "nango.server.app.create_session_factory",
        lambda _engine: FakeSessionFactory(),
    )

    app = create_app(Settings(service_name="test-core", database_url="postgres://test"))

    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        saved = await client.put(
            "/persist/v1/environment/1/connection/10/checkpoint",
            headers=AUTH_HEADER,
            json={"model": "Contact", "key": "sync", "cursor": "cursor-1"},
        )
        loaded = await client.get(
            "/persist/v1/environment/1/connection/10/checkpoint",
            headers=AUTH_HEADER,
            params={"model": "Contact", "key": "sync"},
        )

    assert saved.status_code == 200
    assert loaded.status_code == 200
    assert loaded.json()["checkpoint"]["cursor"] == "cursor-1"
    monkeypatch.undo()
