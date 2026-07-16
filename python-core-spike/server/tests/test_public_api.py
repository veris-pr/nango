from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from nango.api import PublicAPIService
from nango.auth.models import (
    AccountContext,
    AccountSummary,
    EnvironmentSummary,
    SecretSummary,
)
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


async def test_public_connection_route_uses_db_backed_repository_when_configured(
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
            if params == {"environment_id": 1, "provider_config_key": "github-prod"}:
                return FakeResult(
                    [
                        {
                            "id": 1,
                            "environment_id": 1,
                            "unique_key": "github-prod",
                            "provider": "github",
                            "oauth_client_id": "client-id",
                            "oauth_scopes": None,
                            "forward_webhooks": True,
                            "missing_fields": [],
                            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            if params == {
                "environment_id": 1,
                "provider_config_key": "github-prod",
                "connection_id": "conn-1",
            }:
                return FakeResult(
                    [
                        {
                            "id": 42,
                            "config_id": 1,
                            "environment_id": 1,
                            "provider_config_key": "github-prod",
                            "connection_id": "conn-1",
                            "connection_config": {"base_url": "https://api.github.com"},
                            "metadata": {"team": "platform"},
                            "tags": {"region": "us"},
                            "end_user": {
                                "id": 7,
                                "end_user_id": "user-1",
                                "account_id": 1,
                                "environment_id": 1,
                                "email": "user@example.com",
                                "display_name": "Ada",
                                "organization_id": "org-1",
                                "organization_display_name": "Platform",
                                "tags": {"tier": "enterprise"},
                                "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                                "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            },
                            "active_logs": [
                                {"type": "auth", "log_id": "log-1"},
                                {"type": "sync", "log_id": "log-2"},
                            ],
                            "credentials": {
                                "type": "OAUTH2",
                                "access_token": "secret-access-token",
                                "refresh_token": "secret-refresh-token",
                            },
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": datetime(2025, 1, 3, 3, 4, 5, tzinfo=UTC),
                            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 4, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            return FakeResult([])

    class FakeSessionFactory:
        def __call__(self) -> FakeSession:
            return FakeSession()

    class StubAuthService:
        def __init__(self, context: AccountContext) -> None:
            self._context = context

        async def get_account_context_by_api_key(
            self,
            *,
            secret_key: str | None = None,
            internal_secret_key: str | None = None,
        ) -> AccountContext | None:
            return self._context if (secret_key or internal_secret_key) else None

    monkeypatch.setattr("nango.server.app.create_engine", lambda _settings: FakeEngine())
    monkeypatch.setattr(
        "nango.server.app.create_session_factory",
        lambda _engine: FakeSessionFactory(),
    )

    now = datetime(2025, 1, 1, tzinfo=UTC)
    auth_context = AccountContext(
        account=AccountSummary(id=1, createdAt=now, updatedAt=now),
        environment=EnvironmentSummary(
            id=1,
            name="dev",
            accountId=1,
            secretKey="secret",
            isProduction=False,
            createdAt=now,
            updatedAt=now,
        ),
        secret=SecretSummary(
            id=1,
            environmentId=1,
            displayName="Default",
            secret="secret",
            hashed="hashed",
            isDefault=True,
            createdAt=now,
            updatedAt=now,
        ),
        authSource="api_secret",
    )

    app = create_app(Settings(service_name="test-core", database_url="postgres://test"))
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        app.state.auth_service = StubAuthService(auth_context)
        fetched = await client.get(
            "/connections/conn-1",
            params={"provider_config_key": "github-prod"},
            headers={"Authorization": "Bearer secret"},
        )
        deprecated = await client.get(
            "/connection/conn-1",
            params={"provider_config_key": "github-prod"},
            headers={"Authorization": "Bearer secret"},
        )

    assert fetched.status_code == 200
    assert fetched.json() == {
        "id": 42,
        "connection_id": "conn-1",
        "provider_config_key": "github-prod",
        "provider": "github",
        "errors": [
            {"type": "auth", "log_id": "log-1"},
            {"type": "sync", "log_id": "log-2"},
        ],
        "end_user": {
            "id": "user-1",
            "display_name": "Ada",
            "email": "user@example.com",
            "tags": {"tier": "enterprise"},
            "organization": {"id": "org-1", "display_name": "Platform"},
        },
        "tags": {"region": "us"},
        "metadata": {"team": "platform"},
        "connection_config": {"base_url": "https://api.github.com"},
        "created_at": "2025-01-02T03:04:05Z",
        "updated_at": "2025-01-04T03:04:05Z",
        "last_fetched_at": "2025-01-03T03:04:05Z",
        "credentials": {
            "type": "OAUTH2",
            "access_token": "secret-access-token",
            "refresh_token": "secret-refresh-token",
        },
    }
    assert deprecated.status_code == 200
    assert deprecated.json() == fetched.json()


async def test_public_connection_route_hides_credentials_for_non_privileged_customer_keys(
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

        def first(self) -> dict[str, object] | None:
            return self._rows[0] if self._rows else None

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def execute(self, _query: object, params: dict[str, object]) -> FakeResult:
            if params == {"environment_id": 1, "provider_config_key": "github-prod"}:
                return FakeResult(
                    [
                        {
                            "id": 1,
                            "environment_id": 1,
                            "unique_key": "github-prod",
                            "provider": "github",
                            "oauth_client_id": None,
                            "oauth_scopes": None,
                            "forward_webhooks": True,
                            "missing_fields": [],
                            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            if params == {
                "environment_id": 1,
                "provider_config_key": "github-prod",
                "connection_id": "conn-1",
            }:
                return FakeResult(
                    [
                        {
                            "id": 42,
                            "config_id": 1,
                            "environment_id": 1,
                            "provider_config_key": "github-prod",
                            "connection_id": "conn-1",
                            "connection_config": {},
                            "metadata": None,
                            "tags": {},
                            "credentials": {"access_token": "secret-access-token"},
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": None,
                            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 4, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            return FakeResult([])

    class FakeSessionFactory:
        def __call__(self) -> FakeSession:
            return FakeSession()

    class StubAuthService:
        def __init__(self, context: AccountContext) -> None:
            self._context = context

        async def get_account_context_by_api_key(
            self,
            *,
            secret_key: str | None = None,
            internal_secret_key: str | None = None,
        ) -> AccountContext | None:
            return self._context if (secret_key or internal_secret_key) else None

    monkeypatch.setattr("nango.server.app.create_engine", lambda _settings: FakeEngine())
    monkeypatch.setattr(
        "nango.server.app.create_session_factory",
        lambda _engine: FakeSessionFactory(),
    )

    now = datetime(2025, 1, 1, tzinfo=UTC)
    auth_context = AccountContext(
        account=AccountSummary(id=1, createdAt=now, updatedAt=now),
        environment=EnvironmentSummary(
            id=1,
            name="dev",
            accountId=1,
            secretKey="secret",
            isProduction=False,
            createdAt=now,
            updatedAt=now,
        ),
        secret=SecretSummary(
            id=1,
            environmentId=1,
            displayName="Default",
            secret="secret",
            hashed="hashed",
            isDefault=True,
            createdAt=now,
            updatedAt=now,
        ),
        authSource="customer_key",
        scopes=("environment:connections:read",),
    )

    app = create_app(Settings(service_name="test-core", database_url="postgres://test"))
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        app.state.auth_service = StubAuthService(auth_context)
        fetched = await client.get(
            "/connections/conn-1",
            params={"provider_config_key": "github-prod"},
            headers={"Authorization": "Bearer limited-secret"},
        )

    assert fetched.status_code == 200
    assert fetched.json()["credentials"] == {}


async def test_public_connections_route_lists_db_backed_connections(
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
            if params == {
                "environment_id": 1,
                "connection_id": None,
                "provider_config_keys": [],
                "end_user_id": None,
                "end_user_organization_id": None,
                "search_pattern": None,
                "tags": None,
                "limit": 10000,
                "offset": 0,
            }:
                return FakeResult(
                    [
                        {
                            "id": 42,
                            "config_id": 1,
                            "environment_id": 1,
                            "provider_config_key": "github-prod",
                            "connection_id": "conn-1",
                            "connection_config": {},
                            "metadata": {"team": "platform"},
                            "tags": {"region": "us"},
                            "end_user": {
                                "id": 7,
                                "end_user_id": "user-1",
                                "account_id": 1,
                                "environment_id": 1,
                                "email": "user@example.com",
                                "display_name": "Ada",
                                "organization_id": None,
                                "organization_display_name": None,
                                "tags": {"tier": "enterprise"},
                                "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                                "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            },
                            "active_logs": [{"type": "auth", "log_id": "log-1"}],
                            "credentials": {},
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": None,
                            "created_at": datetime(2025, 1, 4, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 4, 3, 4, 5, tzinfo=UTC),
                        },
                        {
                            "id": 41,
                            "config_id": 2,
                            "environment_id": 1,
                            "provider_config_key": "slack-prod",
                            "connection_id": "conn-2",
                            "connection_config": {},
                            "metadata": None,
                            "tags": {},
                            "end_user": None,
                            "active_logs": [],
                            "credentials": {},
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": None,
                            "created_at": datetime(2025, 1, 3, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 3, 3, 4, 5, tzinfo=UTC),
                        },
                    ]
                )
            if params == {"environment_id": 1, "provider_config_key": "github-prod"}:
                return FakeResult(
                    [
                        {
                            "id": 1,
                            "environment_id": 1,
                            "unique_key": "github-prod",
                            "provider": "github",
                            "oauth_client_id": None,
                            "oauth_scopes": None,
                            "forward_webhooks": True,
                            "missing_fields": [],
                            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            if params == {"environment_id": 1, "provider_config_key": "slack-prod"}:
                return FakeResult(
                    [
                        {
                            "id": 2,
                            "environment_id": 1,
                            "unique_key": "slack-prod",
                            "provider": "slack",
                            "oauth_client_id": None,
                            "oauth_scopes": None,
                            "forward_webhooks": True,
                            "missing_fields": [],
                            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            return FakeResult([])

    class FakeSessionFactory:
        def __call__(self) -> FakeSession:
            return FakeSession()

    class StubAuthService:
        def __init__(self, context: AccountContext) -> None:
            self._context = context

        async def get_account_context_by_api_key(
            self,
            *,
            secret_key: str | None = None,
            internal_secret_key: str | None = None,
        ) -> AccountContext | None:
            return self._context if (secret_key or internal_secret_key) else None

    monkeypatch.setattr("nango.server.app.create_engine", lambda _settings: FakeEngine())
    monkeypatch.setattr(
        "nango.server.app.create_session_factory",
        lambda _engine: FakeSessionFactory(),
    )

    now = datetime(2025, 1, 1, tzinfo=UTC)
    auth_context = AccountContext(
        account=AccountSummary(id=1, createdAt=now, updatedAt=now),
        environment=EnvironmentSummary(
            id=1,
            name="dev",
            accountId=1,
            secretKey="secret",
            isProduction=False,
            createdAt=now,
            updatedAt=now,
        ),
        secret=SecretSummary(
            id=1,
            environmentId=1,
            displayName="Default",
            secret="secret",
            hashed="hashed",
            isDefault=True,
            createdAt=now,
            updatedAt=now,
        ),
        authSource="api_secret",
    )

    app = create_app(Settings(service_name="test-core", database_url="postgres://test"))
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        app.state.auth_service = StubAuthService(auth_context)
        fetched = await client.get(
            "/connections",
            headers={"Authorization": "Bearer secret"},
        )
        deprecated = await client.get(
            "/connection",
            headers={"Authorization": "Bearer secret"},
        )

    assert fetched.status_code == 200
    assert fetched.json() == {
        "connections": [
            {
                "id": 42,
                "connection_id": "conn-1",
                "provider_config_key": "github-prod",
                "created": "2025-01-04T03:04:05Z",
                "metadata": {"team": "platform"},
                "provider": "github",
                "errors": [{"type": "auth", "log_id": "log-1"}],
                "end_user": {
                    "id": "user-1",
                    "display_name": "Ada",
                    "email": "user@example.com",
                    "tags": {"tier": "enterprise"},
                },
                "tags": {"region": "us"},
            },
            {
                "id": 41,
                "connection_id": "conn-2",
                "provider_config_key": "slack-prod",
                "created": "2025-01-03T03:04:05Z",
                "provider": "slack",
                "errors": [],
                "tags": {},
            },
        ]
    }
    assert deprecated.status_code == 200
    assert deprecated.json() == fetched.json()


async def test_public_connections_route_filters_by_integration_id(
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
            if params == {
                "environment_id": 1,
                "connection_id": None,
                "provider_config_keys": ["github-prod"],
                "end_user_id": None,
                "end_user_organization_id": None,
                "search_pattern": None,
                "tags": None,
                "limit": 10000,
                "offset": 0,
            }:
                return FakeResult(
                    [
                        {
                            "id": 42,
                            "config_id": 1,
                            "environment_id": 1,
                            "provider_config_key": "github-prod",
                            "connection_id": "conn-1",
                            "connection_config": {},
                            "metadata": None,
                            "tags": {},
                            "end_user": None,
                            "active_logs": [{"type": "sync", "log_id": "log-9"}],
                            "credentials": {},
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": None,
                            "created_at": datetime(2025, 1, 4, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 4, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            if params == {"environment_id": 1, "provider_config_key": "github-prod"}:
                return FakeResult(
                    [
                        {
                            "id": 1,
                            "environment_id": 1,
                            "unique_key": "github-prod",
                            "provider": "github",
                            "oauth_client_id": None,
                            "oauth_scopes": None,
                            "forward_webhooks": True,
                            "missing_fields": [],
                            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            return FakeResult([])

    class FakeSessionFactory:
        def __call__(self) -> FakeSession:
            return FakeSession()

    class StubAuthService:
        def __init__(self, context: AccountContext) -> None:
            self._context = context

        async def get_account_context_by_api_key(
            self,
            *,
            secret_key: str | None = None,
            internal_secret_key: str | None = None,
        ) -> AccountContext | None:
            return self._context if (secret_key or internal_secret_key) else None

    monkeypatch.setattr("nango.server.app.create_engine", lambda _settings: FakeEngine())
    monkeypatch.setattr(
        "nango.server.app.create_session_factory",
        lambda _engine: FakeSessionFactory(),
    )

    now = datetime(2025, 1, 1, tzinfo=UTC)
    auth_context = AccountContext(
        account=AccountSummary(id=1, createdAt=now, updatedAt=now),
        environment=EnvironmentSummary(
            id=1,
            name="dev",
            accountId=1,
            secretKey="secret",
            isProduction=False,
            createdAt=now,
            updatedAt=now,
        ),
        secret=SecretSummary(
            id=1,
            environmentId=1,
            displayName="Default",
            secret="secret",
            hashed="hashed",
            isDefault=True,
            createdAt=now,
            updatedAt=now,
        ),
        authSource="api_secret",
    )

    app = create_app(Settings(service_name="test-core", database_url="postgres://test"))
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        app.state.auth_service = StubAuthService(auth_context)
        fetched = await client.get(
            "/connections",
            params={"integrationId": "github-prod"},
            headers={"Authorization": "Bearer secret"},
        )

    assert fetched.status_code == 200
    assert fetched.json() == {
        "connections": [
            {
                "id": 42,
                "connection_id": "conn-1",
                "provider_config_key": "github-prod",
                "created": "2025-01-04T03:04:05Z",
                "provider": "github",
                "errors": [{"type": "sync", "log_id": "log-9"}],
                "tags": {},
            }
        ]
    }


async def test_public_connections_route_filters_by_search_end_user_and_tags(
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
            if params == {
                "environment_id": 1,
                "connection_id": None,
                "provider_config_keys": [],
                "end_user_id": None,
                "end_user_organization_id": None,
                "search_pattern": "%Ada%",
                "tags": None,
                "limit": 10000,
                "offset": 0,
            }:
                return FakeResult(
                    [
                        {
                            "id": 42,
                            "config_id": 1,
                            "environment_id": 1,
                            "provider_config_key": "github-prod",
                            "connection_id": "conn-ada",
                            "connection_config": {},
                            "metadata": None,
                            "tags": {},
                            "end_user": {
                                "id": 7,
                                "end_user_id": "user-ada",
                                "account_id": 1,
                                "environment_id": 1,
                                "email": "ada@example.com",
                                "display_name": "Ada Lovelace",
                                "organization_id": "org-1",
                                "organization_display_name": "Platform",
                                "tags": None,
                                "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                                "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            },
                            "active_logs": [],
                            "credentials": {},
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": None,
                            "created_at": datetime(2025, 1, 4, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 4, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            if params == {
                "environment_id": 1,
                "connection_id": None,
                "provider_config_keys": [],
                "end_user_id": "user-ada",
                "end_user_organization_id": None,
                "search_pattern": None,
                "tags": None,
                "limit": 10000,
                "offset": 0,
            }:
                return FakeResult(
                    [
                        {
                            "id": 42,
                            "config_id": 1,
                            "environment_id": 1,
                            "provider_config_key": "github-prod",
                            "connection_id": "conn-ada",
                            "connection_config": {},
                            "metadata": None,
                            "tags": {},
                            "end_user": {
                                "id": 7,
                                "end_user_id": "user-ada",
                                "account_id": 1,
                                "environment_id": 1,
                                "email": "ada@example.com",
                                "display_name": "Ada Lovelace",
                                "organization_id": "org-1",
                                "organization_display_name": "Platform",
                                "tags": None,
                                "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                                "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            },
                            "active_logs": [],
                            "credentials": {},
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": None,
                            "created_at": datetime(2025, 1, 4, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 4, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            if params == {
                "environment_id": 1,
                "connection_id": None,
                "provider_config_keys": [],
                "end_user_id": None,
                "end_user_organization_id": "org-1",
                "search_pattern": None,
                "tags": None,
                "limit": 10000,
                "offset": 0,
            }:
                return FakeResult(
                    [
                        {
                            "id": 42,
                            "config_id": 1,
                            "environment_id": 1,
                            "provider_config_key": "github-prod",
                            "connection_id": "conn-ada",
                            "connection_config": {},
                            "metadata": None,
                            "tags": {},
                            "end_user": {
                                "id": 7,
                                "end_user_id": "user-ada",
                                "account_id": 1,
                                "environment_id": 1,
                                "email": "ada@example.com",
                                "display_name": "Ada Lovelace",
                                "organization_id": "org-1",
                                "organization_display_name": "Platform",
                                "tags": None,
                                "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                                "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            },
                            "active_logs": [],
                            "credentials": {},
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": None,
                            "created_at": datetime(2025, 1, 4, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 4, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            if params == {
                "environment_id": 1,
                "connection_id": None,
                "provider_config_keys": [],
                "end_user_id": None,
                "end_user_organization_id": None,
                "search_pattern": None,
                "tags": '{"department": "engineering", "env": "prod"}',
                "limit": 10000,
                "offset": 0,
            }:
                return FakeResult(
                    [
                        {
                            "id": 43,
                            "config_id": 1,
                            "environment_id": 1,
                            "provider_config_key": "github-prod",
                            "connection_id": "conn-tags",
                            "connection_config": {},
                            "metadata": None,
                            "tags": {"department": "engineering", "env": "prod"},
                            "end_user": None,
                            "active_logs": [],
                            "credentials": {},
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": None,
                            "created_at": datetime(2025, 1, 5, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 5, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            if params == {"environment_id": 1, "provider_config_key": "github-prod"}:
                return FakeResult(
                    [
                        {
                            "id": 1,
                            "environment_id": 1,
                            "unique_key": "github-prod",
                            "provider": "github",
                            "oauth_client_id": None,
                            "oauth_scopes": None,
                            "forward_webhooks": True,
                            "missing_fields": [],
                            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            return FakeResult([])

    class FakeSessionFactory:
        def __call__(self) -> FakeSession:
            return FakeSession()

    class StubAuthService:
        def __init__(self, context: AccountContext) -> None:
            self._context = context

        async def get_account_context_by_api_key(
            self,
            *,
            secret_key: str | None = None,
            internal_secret_key: str | None = None,
        ) -> AccountContext | None:
            return self._context if (secret_key or internal_secret_key) else None

    monkeypatch.setattr("nango.server.app.create_engine", lambda _settings: FakeEngine())
    monkeypatch.setattr(
        "nango.server.app.create_session_factory",
        lambda _engine: FakeSessionFactory(),
    )

    now = datetime(2025, 1, 1, tzinfo=UTC)
    auth_context = AccountContext(
        account=AccountSummary(id=1, createdAt=now, updatedAt=now),
        environment=EnvironmentSummary(
            id=1,
            name="dev",
            accountId=1,
            secretKey="secret",
            isProduction=False,
            createdAt=now,
            updatedAt=now,
        ),
        secret=SecretSummary(
            id=1,
            environmentId=1,
            displayName="Default",
            secret="secret",
            hashed="hashed",
            isDefault=True,
            createdAt=now,
            updatedAt=now,
        ),
        authSource="api_secret",
    )

    app = create_app(Settings(service_name="test-core", database_url="postgres://test"))
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        app.state.auth_service = StubAuthService(auth_context)
        by_search = await client.get(
            "/connections",
            params={"search": "Ada"},
            headers={"Authorization": "Bearer secret"},
        )
        by_user = await client.get(
            "/connections",
            params={"endUserId": "user-ada"},
            headers={"Authorization": "Bearer secret"},
        )
        by_org = await client.get(
            "/connections",
            params={"endUserOrganizationId": "org-1"},
            headers={"Authorization": "Bearer secret"},
        )
        by_tags = await client.get(
            "/connections?tags[department]=engineering&tags[env]=prod",
            headers={"Authorization": "Bearer secret"},
        )

    assert by_search.status_code == 200
    assert by_search.json()["connections"][0]["connection_id"] == "conn-ada"
    assert by_user.status_code == 200
    assert by_user.json()["connections"][0]["end_user"]["id"] == "user-ada"
    assert by_org.status_code == 200
    assert by_org.json()["connections"][0]["end_user"]["id"] == "user-ada"
    assert by_tags.status_code == 200
    assert by_tags.json()["connections"][0]["connection_id"] == "conn-tags"


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
                "connection": {
                    "id": 1,
                    "connectionId": "conn-1",
                    "providerConfigKey": "github-prod",
                    "environmentId": 1,
                },
            },
        )
        action = await client.post(
            "/action/trigger",
            json={
                "actionName": "createIssue",
                "input": {"title": "Bug"},
                "connection": {
                    "id": 1,
                    "connectionId": "conn-1",
                    "providerConfigKey": "github-prod",
                    "environmentId": 1,
                },
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


async def test_action_trigger_accepts_ts_style_headers(
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

        def first(self) -> dict[str, object] | None:
            return self._rows[0] if self._rows else None

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def execute(self, _query: object, params: dict[str, object]) -> FakeResult:
            if params == {
                "environment_id": 1,
                "provider_config_key": "github-prod",
                "connection_id": "conn-1",
            }:
                return FakeResult(
                    [
                        {
                            "id": 1,
                            "config_id": 1,
                            "environment_id": 1,
                            "provider_config_key": "github-prod",
                            "connection_id": "conn-1",
                            "connection_config": {},
                            "metadata": None,
                            "tags": {},
                            "end_user": None,
                            "active_logs": [],
                            "credentials": {},
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": None,
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

    orchestrator = OrchestratorService()
    app = create_app(
        Settings(service_name="test-core", database_url="postgres://test"),
        orchestrator_service=orchestrator,
    )

    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        action = await client.post(
            "/action/trigger",
            json={"action_name": "createIssue", "input": {"title": "Bug"}},
            headers={
                "provider-config-key": "github-prod",
                "connection-id": "conn-1",
                "x-async": "true",
                "x-max-retries": "5",
            },
        )
        dequeued = await client.post(
            "/orchestrator/v1/dequeue",
            json={"groupKeyPattern": "*", "limit": 1, "longPolling": False},
        )

    assert action.status_code == 200
    assert action.json()["data"]["type"] == "action"
    [task] = dequeued.json()
    assert task["retryMax"] == 5
    assert task["payload"] == {
        "type": "action",
        "actionName": "createIssue",
        "activityLogId": task["payload"]["activityLogId"],
        "input": {"title": "Bug"},
        "async": True,
        "connection": {
            "id": 1,
            "connection_id": "conn-1",
            "provider_config_key": "github-prod",
            "environment_id": 1,
        },
    }


async def test_triggers_use_db_backed_connection_identity_when_configured(
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
            if params == {
                "environment_id": 1,
                "provider_config_key": "github-prod",
                "connection_id": "conn-42",
            }:
                return FakeResult(
                    [
                        {
                            "id": 42,
                            "config_id": 1,
                            "environment_id": 1,
                            "provider_config_key": "github-prod",
                            "connection_id": "conn-42",
                            "connection_config": {},
                            "metadata": None,
                            "tags": {},
                            "end_user": None,
                            "active_logs": [],
                            "credentials": {},
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": None,
                            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            if params == {
                "connection_id": 42,
                "name": "issues",
                "variant": "base",
            }:
                return FakeResult(
                    [
                        {
                            "id": "sync-issues-base",
                            "nango_connection_id": 42,
                            "name": "issues",
                            "variant": "base",
                            "frequency": None,
                            "last_sync_date": None,
                            "sync_config_id": 7,
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

    orchestrator = OrchestratorService()
    app = create_app(
        Settings(service_name="test-core", database_url="postgres://test"),
        orchestrator_service=orchestrator,
    )

    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        sync = await client.post(
            "/sync/trigger",
            json={
                "syncName": "issues",
                "connectionId": "conn-42",
                "providerConfigKey": "github-prod",
            },
        )
        action = await client.post(
            "/action/trigger",
            json={
                "actionName": "createIssue",
                "input": {"title": "Bug"},
                "connectionId": "conn-42",
                "providerConfigKey": "github-prod",
            },
        )
        dequeued = await client.post(
            "/orchestrator/v1/dequeue",
            json={"groupKeyPattern": "*", "limit": 2, "longPolling": False},
        )

    assert sync.status_code == 200
    assert action.status_code == 200
    task_payloads = [task["payload"] for task in dequeued.json()]
    assert {payload["connection"]["id"] for payload in task_payloads} == {42}
    assert {payload["connection"]["connection_id"] for payload in task_payloads} == {"conn-42"}
    assert {payload.get("syncId") for payload in task_payloads if payload["type"] == "sync"} == {
        "sync-issues-base"
    }


async def test_sync_trigger_accepts_ts_style_single_sync_request(
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

        def first(self) -> dict[str, object] | None:
            return self._rows[0] if self._rows else None

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def execute(self, _query: object, params: dict[str, object]) -> FakeResult:
            if params == {
                "environment_id": 1,
                "provider_config_key": "github-prod",
                "connection_id": "conn-42",
            }:
                return FakeResult(
                    [
                        {
                            "id": 42,
                            "config_id": 1,
                            "environment_id": 1,
                            "provider_config_key": "github-prod",
                            "connection_id": "conn-42",
                            "connection_config": {},
                            "metadata": None,
                            "tags": {},
                            "end_user": None,
                            "active_logs": [],
                            "credentials": {},
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": None,
                            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            if params == {
                "connection_id": 42,
                "name": "issues",
                "variant": "custom",
            }:
                return FakeResult(
                    [
                        {
                            "id": "sync-issues-custom",
                            "nango_connection_id": 42,
                            "name": "issues",
                            "variant": "custom",
                            "frequency": None,
                            "last_sync_date": None,
                            "sync_config_id": 7,
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

    orchestrator = OrchestratorService()
    app = create_app(
        Settings(service_name="test-core", database_url="postgres://test"),
        orchestrator_service=orchestrator,
    )

    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/sync/trigger",
            json={"syncs": ["issues::custom"]},
            headers={
                "provider-config-key": "github-prod",
                "connection-id": "conn-42",
            },
        )
        dequeued = await client.post(
            "/orchestrator/v1/dequeue",
            json={"groupKeyPattern": "*", "limit": 1, "longPolling": False},
        )

    assert response.status_code == 200
    assert response.json()["data"]["type"] == "sync"
    [task] = dequeued.json()
    assert task["payload"] == {
        "type": "sync",
        "syncId": "sync-issues-custom",
        "syncName": "issues",
        "syncVariant": "custom",
        "debug": False,
        "connection": {
            "id": 42,
            "connection_id": "conn-42",
            "provider_config_key": "github-prod",
            "environment_id": 1,
        },
    }


async def test_sync_trigger_accepts_ts_style_multi_sync_request(
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

        def first(self) -> dict[str, object] | None:
            return self._rows[0] if self._rows else None

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def execute(self, _query: object, params: dict[str, object]) -> FakeResult:
            if params == {
                "environment_id": 1,
                "provider_config_key": "github-prod",
                "connection_id": "conn-42",
            }:
                return FakeResult(
                    [
                        {
                            "id": 42,
                            "config_id": 1,
                            "environment_id": 1,
                            "provider_config_key": "github-prod",
                            "connection_id": "conn-42",
                            "connection_config": {},
                            "metadata": None,
                            "tags": {},
                            "end_user": None,
                            "active_logs": [],
                            "credentials": {},
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": None,
                            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                            "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
                        }
                    ]
                )
            if params == {
                "connection_id": 42,
                "name": "issues",
                "variant": "base",
            }:
                return FakeResult(
                    [
                        {
                            "id": "sync-issues-base",
                            "nango_connection_id": 42,
                            "name": "issues",
                            "variant": "base",
                            "frequency": None,
                            "last_sync_date": None,
                            "sync_config_id": 7,
                        }
                    ]
                )
            if params == {
                "connection_id": 42,
                "name": "pulls",
                "variant": "custom",
            }:
                return FakeResult(
                    [
                        {
                            "id": "sync-pulls-custom",
                            "nango_connection_id": 42,
                            "name": "pulls",
                            "variant": "custom",
                            "frequency": None,
                            "last_sync_date": None,
                            "sync_config_id": 8,
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

    orchestrator = OrchestratorService()
    app = create_app(
        Settings(service_name="test-core", database_url="postgres://test"),
        orchestrator_service=orchestrator,
    )

    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/sync/trigger",
            json={
                "syncs": ["issues", {"name": "pulls", "variant": "custom"}],
                "provider_config_key": "github-prod",
                "connection_id": "conn-42",
            },
        )
        dequeued = await client.post(
            "/orchestrator/v1/dequeue",
            json={"groupKeyPattern": "*", "limit": 2, "longPolling": False},
        )

    assert response.status_code == 200
    assert response.json() == {"success": True}
    payloads = [task["payload"] for task in dequeued.json()]
    assert {payload["syncId"] for payload in payloads} == {
        "sync-issues-base",
        "sync-pulls-custom",
    }
    assert {(payload["syncName"], payload["syncVariant"]) for payload in payloads} == {
        ("issues", "base"),
        ("pulls", "custom"),
    }
    assert {payload["connection"]["connection_id"] for payload in payloads} == {"conn-42"}


async def test_sync_trigger_returns_no_syncs_found_when_sync_row_is_missing(
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

        def first(self) -> dict[str, object] | None:
            return self._rows[0] if self._rows else None

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def execute(self, _query: object, params: dict[str, object]) -> FakeResult:
            if params == {
                "environment_id": 1,
                "provider_config_key": "github-prod",
                "connection_id": "conn-42",
            }:
                return FakeResult(
                    [
                        {
                            "id": 42,
                            "config_id": 1,
                            "environment_id": 1,
                            "provider_config_key": "github-prod",
                            "connection_id": "conn-42",
                            "connection_config": {},
                            "metadata": None,
                            "tags": {},
                            "end_user": None,
                            "active_logs": [],
                            "credentials": {},
                            "credentials_iv": None,
                            "credentials_tag": None,
                            "last_fetched_at": None,
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
        response = await client.post(
            "/sync/trigger",
            json={
                "syncs": ["issues"],
                "provider_config_key": "github-prod",
                "connection_id": "conn-42",
            },
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "no_syncs_found",
            "message": "No syncs found given the inputs.",
        }
    }


async def test_sync_trigger_rejects_unsupported_full_refresh_modes() -> None:
    app = create_app(Settings(service_name="test-core"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/sync/trigger",
            json={
                "syncs": ["issues"],
                "provider_config_key": "github-prod",
                "connection_id": "conn-42",
                "sync_mode": "full_refresh",
            },
        )

    assert response.status_code == 501
    assert response.json() == {
        "error": {
            "code": "sync_trigger_not_implemented",
            "message": "Python sync trigger does not yet support full refresh modes",
        }
    }


async def test_sync_trigger_rejects_opts_with_legacy_sync_parameters() -> None:
    app = create_app(Settings(service_name="test-core"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/sync/trigger",
            json={
                "syncs": ["issues"],
                "provider_config_key": "github-prod",
                "connection_id": "conn-42",
                "opts": {"reset": True},
                "sync_mode": "incremental",
            },
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_body",
            "message": "Cannot use opts with deprecated sync_mode/full_resync parameters",
        }
    }


async def test_triggers_return_not_found_for_missing_db_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEngine:
        async def dispose(self) -> None:
            return None

    class FakeResult:
        def mappings(self) -> FakeResult:
            return self

        def first(self) -> dict[str, object] | None:
            return None

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def execute(self, _query: object, _params: dict[str, object]) -> FakeResult:
            return FakeResult()

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
        response = await client.post(
            "/sync/trigger",
            json={
                "syncName": "issues",
                "connectionId": "missing",
                "providerConfigKey": "github-prod",
            },
        )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "connection_not_found",
            "message": 'Connection "missing" was not found',
        }
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
