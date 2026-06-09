from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from nango.api import PublicAPIService
from nango.domain.repositories import InMemoryIntegrationConfigRepository
from nango.orchestrator import OrchestratorService
from nango.server.app import create_app
from nango.server.settings import Settings


async def test_provider_routes_list_and_read_catalog() -> None:
    app = create_app(
        Settings(service_name="test-core"),
        public_api_service=PublicAPIService(
            providers={
                "github": {"display_name": "GitHub", "auth_mode": "OAUTH2"},
                "slack": {"display_name": "Slack", "auth_mode": "OAUTH2"},
            }
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get("/providers")
        fetched = await client.get("/providers/github")

    assert listed.status_code == 200
    assert [provider["provider"] for provider in listed.json()["data"]] == ["github", "slack"]
    assert fetched.status_code == 200
    assert fetched.json()["data"] == {
        "provider": "github",
        "display_name": "GitHub",
        "auth_mode": "OAUTH2",
    }


async def test_integration_routes_list_read_and_error_envelope() -> None:
    integrations = InMemoryIntegrationConfigRepository()
    integrations.create(
        environment_id=1,
        provider_config_key="github-prod",
        provider="github",
        oauth_client_id="client-id",
    )
    app = create_app(
        Settings(service_name="test-core"),
        public_api_service=PublicAPIService(integrations=integrations),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get("/integrations")
        fetched = await client.get("/integrations/github-prod")
        missing = await client.get("/integrations/missing")

    assert listed.status_code == 200
    assert listed.json()["data"][0]["providerConfigKey"] == "github-prod"
    assert fetched.status_code == 200
    assert fetched.json()["data"]["provider"] == "github"
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {
            "code": "integration_not_found",
            "message": 'Integration "missing" was not found',
        }
    }


async def test_integration_routes_use_db_backed_repository_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEngine:
        async def dispose(self) -> None:
            return None

    class FakeResult:
        def __init__(self, rows: list[dict[str, object]]) -> None:
            self._rows = rows

        def mappings(self) -> FakeResult:
            return self

        def all(self) -> list[dict[str, object]]:
            return self._rows

        def first(self) -> dict[str, object] | None:
            return self._rows[0] if self._rows else None

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def execute(self, _query: object, params: dict[str, object]) -> FakeResult:
            if params == {"environment_id": 1}:
                return FakeResult(
                    [
                        {
                            "id": 1,
                            "environment_id": 1,
                            "unique_key": "github-prod",
                            "provider": "github",
                            "oauth_client_id": "client-id",
                            "oauth_scopes": "repo,read:user",
                            "forward_webhooks": True,
                            "missing_fields": ["oauth_client_id"],
                            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            return FakeResult([])

    class FakeSessionFactory:
        def __call__(self) -> FakeSession:
            return FakeSession()

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
        listed = await client.get("/integrations")

    assert listed.status_code == 200
    assert listed.json()["data"] == [
        {
            "id": 1,
            "environmentId": 1,
            "providerConfigKey": "github-prod",
            "provider": "github",
            "oauthClientId": "client-id",
            "oauthScopes": ["repo", "read:user"],
            "forwardWebhooks": True,
            "missingFields": ["oauth_client_id"],
            "createdAt": "2025-01-02T03:04:05Z",
            "updatedAt": "2025-01-02T03:04:05Z",
        }
    ]


async def test_connect_session_create_and_get_token_shape() -> None:
    app = create_app(Settings(service_name="test-core"))
    body = {"end_user": {"id": "user-1", "email": "user@example.com"}}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/connect/sessions", json=body)
        token = created.json()["data"]["token"]
        fetched = await client.get("/connect/session", headers={"Authorization": f"Bearer {token}"})

    assert created.status_code == 200
    assert token.startswith("nango_connect_session_")
    assert created.json()["data"]["connect_link"].endswith(f"session_token={token}")
    assert "expires_at" in created.json()["data"]
    assert fetched.status_code == 200
    assert fetched.json()["data"]["token"] == token
    assert fetched.json()["data"]["request"] == body


async def test_deploy_validation_uses_python_nango_yaml_parser() -> None:
    app = create_app(Settings(service_name="test-core"))
    valid_yaml = """
integrations:
  github:
    syncs:
      issues:
        runs: every hour
        output: Issue
models:
  Issue:
    id: string
"""

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        valid = await client.post("/sync/deploy", json={"yaml": valid_yaml})
        invalid = await client.post("/sync/deploy", json={"yaml": "models: []"})

    assert valid.status_code == 200
    assert valid.json()["data"]["valid"] is True
    assert valid.json()["data"]["metadata"]["modelNames"] == ["Issue"]
    assert invalid.status_code == 200
    assert invalid.json()["data"]["valid"] is False
    assert invalid.json()["data"]["errors"][0]["code"] == "invalid_top_level_shape"


async def test_sync_and_action_triggers_create_orchestrator_tasks() -> None:
    orchestrator = OrchestratorService()
    app = create_app(
        Settings(service_name="test-core"),
        orchestrator_service=orchestrator,
        public_api_service=PublicAPIService(orchestrator=orchestrator),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sync = await client.post(
            "/sync/trigger",
            json={
                "syncName": "issues",
                "connectionId": "conn-1",
                "providerConfigKey": "github-prod",
            },
        )
        action = await client.post(
            "/action/trigger",
            json={
                "actionName": "createIssue",
                "input": {"title": "Bug"},
                "connectionId": "conn-1",
                "providerConfigKey": "github-prod",
            },
        )
        dequeued = await client.post(
            "/orchestrator/v1/dequeue",
            json={"groupKeyPattern": "*", "limit": 2, "longPolling": False},
        )

    assert sync.status_code == 200
    assert sync.json()["data"]["type"] == "sync"
    assert action.status_code == 200
    assert action.json()["data"]["type"] == "action"
    task_payloads = [task["payload"] for task in dequeued.json()]
    assert {payload["type"] for payload in task_payloads} == {"sync", "action"}
    assert {payload["connection"]["provider_config_key"] for payload in task_payloads} == {
        "github-prod"
    }


async def test_telemetry_and_billing_routes_are_not_registered() -> None:
    app = create_app(Settings(service_name="test-core"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        telemetry = await client.post("/connect/telemetry", json={})
        billing = await client.get("/plans/current")

    assert telemetry.status_code == 404
    assert billing.status_code == 404
    assert telemetry.json()["error"]["code"] == "route_not_found"
    assert billing.json()["error"]["code"] == "route_not_found"
