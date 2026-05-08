from __future__ import annotations

import ssl
from typing import Any
from unittest.mock import Mock

import pytest

from nango.adapters import database


def test_database_settings_match_nango_env_conventions() -> None:
    settings = database.DatabaseSettings.from_env(
        {
            "SERVER_RUN_MODE": "DOCKERIZED",
            "NANGO_DB_USER": "nango user",
            "NANGO_DB_PASSWORD": "pa/ss",
            "NANGO_DB_PORT": "6543",
            "NANGO_DB_NAME": "nango core",
            "NANGO_DB_SSL": "true",
            "NANGO_DB_SCHEMA": "tenant",
            "NANGO_DB_ADDITIONAL_SCHEMAS": " audit, jobs ,,",
            "NANGO_DB_POOL_MIN": "1",
            "NANGO_DB_POOL_MAX": "9",
            "NANGO_DB_APPLICATION_NAME": "python-core",
        }
    )

    assert settings.url == "postgres://nango%20user:pa%2Fss@nango-db:6543/nango%20core"
    assert settings.async_url == (
        "postgresql+asyncpg://nango%20user:pa%2Fss@nango-db:6543/nango%20core"
    )
    assert settings.ssl_enabled is True
    assert settings.search_path == ("tenant", "public", "audit", "jobs")
    assert settings.pool_min_size == 1
    assert settings.pool_max_size == 9
    assert settings.application_name == "python-core"


def test_database_url_env_takes_precedence() -> None:
    settings = database.DatabaseSettings.from_env(
        {
            "NANGO_DATABASE_URL": "postgresql://user:secret@db.example/nango",
            "NANGO_DB_READ_URL": "postgres://readonly:secret@db.example/nango",
        }
    )

    assert settings.url == "postgresql://user:secret@db.example/nango"
    assert settings.async_url == "postgresql+asyncpg://user:secret@db.example/nango"
    assert settings.async_read_url == "postgresql+asyncpg://readonly:secret@db.example/nango"


def test_create_engine_uses_asyncpg_without_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    create_async_engine = Mock(return_value=object())
    monkeypatch.setattr(database, "create_async_engine", create_async_engine)
    settings = database.DatabaseSettings.from_env(
        {
            "NANGO_DATABASE_URL": "postgres://user:secret@localhost:5432/nango",
            "NANGO_DB_SSL": "true",
            "NANGO_DB_SCHEMA": "nango",
            "NANGO_DB_ADDITIONAL_SCHEMAS": "analytics",
            "NANGO_DB_POOL_MAX": "5",
            "NANGO_DB_APPLICATION_NAME": "test-core",
        }
    )

    engine = database.create_engine(settings)

    assert engine is create_async_engine.return_value
    create_async_engine.assert_called_once()
    args, kwargs = create_async_engine.call_args
    assert args == ("postgresql+asyncpg://user:secret@localhost:5432/nango",)
    assert kwargs["pool_size"] == 5
    assert kwargs["max_overflow"] == 0
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["connect_args"]["server_settings"] == {
        "application_name": "test-core",
        "statement_timeout": "60000",
        "search_path": "nango,public,analytics",
    }
    assert isinstance(kwargs["connect_args"]["ssl"], ssl.SSLContext)


async def test_transaction_yields_session_inside_begin_context() -> None:
    events: list[str] = []

    class BeginContext:
        async def __aenter__(self) -> None:
            events.append("begin")

        async def __aexit__(self, *args: Any) -> None:
            events.append("commit")

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            events.append("open")
            return self

        async def __aexit__(self, *args: Any) -> None:
            events.append("close")

        def begin(self) -> BeginContext:
            return BeginContext()

    class FakeSessionFactory:
        def __call__(self) -> FakeSession:
            return FakeSession()

    async with database.transaction(FakeSessionFactory()) as session:
        assert isinstance(session, FakeSession)
        events.append("work")

    assert events == ["open", "begin", "work", "commit", "close"]


async def test_health_check_runs_select_one() -> None:
    class FakeSession:
        query: object | None = None

        async def scalar(self, query: object) -> int:
            self.query = query
            return 1

    session = FakeSession()

    assert await database.check_database_health(session) is True
    assert str(session.query) == "SELECT 1"


def test_migration_placeholder_points_to_knex_authority() -> None:
    status = database.migration_status()

    assert status.authority == "knex"
    assert status.migrations_path == "packages/database/lib/migrations"
    assert "Knex migrations" in status.message
    with pytest.raises(RuntimeError, match="Knex migrations"):
        database.run_migrations()
