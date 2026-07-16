"""Integration-test harness: migrated Postgres schema.

Starts a Postgres testcontainer, applies the authoritative Knex migrations via
``nango-py/tools/migrate.mjs`` so Python tests run against the exact schema the
TypeScript backend produces, then exposes an async SQLAlchemy session factory.

Migrations run once per session. Each test gets a truncated schema for isolation.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]

NANGO_PY_ROOT = Path(__file__).resolve().parents[2]
MIGRATE_SCRIPT = NANGO_PY_ROOT / "tools" / "migrate.mjs"
SCHEMA = "nango"


def _to_asyncpg_url(container_url: str) -> str:
    return re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", container_url)


def _to_knex_url(container_url: str) -> str:
    return re.sub(r"^postgresql(\+\w+)?://", "postgresql://", container_url)


@pytest.fixture(scope="session")
def pg_container() -> Iterator[PostgresContainer]:
    container = PostgresContainer("postgres:16")
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def migrated_url(pg_container: PostgresContainer) -> str:
    knex_url = _to_knex_url(pg_container.get_connection_url())
    result = subprocess.run(
        ["node", str(MIGRATE_SCRIPT), knex_url, SCHEMA],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "knex migration failed:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    return _to_asyncpg_url(pg_container.get_connection_url())


@pytest_asyncio.fixture(scope="session")
async def db_engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        migrated_url,
        connect_args={"server_settings": {"search_path": SCHEMA}},
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def db_session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _truncate(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        rows = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = :schema"),
            {"schema": SCHEMA},
        )
        tables = [row[0] for row in rows]
        # _nango_auth_migrations tracks applied migrations; keep it.
        tables = [t for t in tables if t != "_nango_auth_migrations"]
        if tables:
            quoted = ", ".join(f'"{t}"' for t in tables)
            await conn.execute(text(f'TRUNCATE {quoted} RESTART IDENTITY CASCADE'))


@pytest_asyncio.fixture
async def clean_db(db_engine: AsyncEngine) -> AsyncEngine:
    await _truncate(db_engine)
    return db_engine