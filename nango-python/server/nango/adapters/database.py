from __future__ import annotations

import ssl
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from os import environ
from typing import Any
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DEFAULT_STATEMENT_TIMEOUT_MS = 60_000
DEFAULT_POOL_MAX_SIZE = 30
MIGRATIONS_AUTHORITY = "Knex migrations in packages/database/lib/migrations remain authoritative."


@dataclass(frozen=True)
class DatabaseSettings:
    url: str
    read_url: str | None
    schema: str
    additional_schemas: tuple[str, ...]
    ssl_enabled: bool
    pool_min_size: int
    pool_max_size: int
    statement_timeout_ms: int
    application_name: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DatabaseSettings:
        source = environ if env is None else env
        host = source.get("NANGO_DB_HOST") or (
            "nango-db" if source.get("SERVER_RUN_MODE") == "DOCKERIZED" else "localhost"
        )
        url = source.get("NANGO_DATABASE_URL") or build_database_url(
            user=source.get("NANGO_DB_USER", "nango"),
            password=source.get("NANGO_DB_PASSWORD", "nango"),
            host=host,
            port=int(source.get("NANGO_DB_PORT", "5432")),
            database=source.get("NANGO_DB_NAME", "nango"),
        )

        return cls(
            url=url,
            read_url=source.get("NANGO_DB_READ_URL"),
            schema=source.get("NANGO_DB_SCHEMA", "nango"),
            additional_schemas=parse_additional_schemas(source.get("NANGO_DB_ADDITIONAL_SCHEMAS")),
            ssl_enabled=source.get("NANGO_DB_SSL", "").lower() == "true",
            pool_min_size=int(source.get("NANGO_DB_POOL_MIN", "0")),
            pool_max_size=int(source.get("NANGO_DB_POOL_MAX", str(DEFAULT_POOL_MAX_SIZE))),
            statement_timeout_ms=int(
                source.get("NANGO_DB_STATEMENT_TIMEOUT_MS", str(DEFAULT_STATEMENT_TIMEOUT_MS))
            ),
            application_name=source.get("NANGO_DB_APPLICATION_NAME", "[unknown]"),
        )

    @property
    def search_path(self) -> tuple[str, ...]:
        return (self.schema, "public", *self.additional_schemas)

    @property
    def async_url(self) -> str:
        return to_asyncpg_url(self.url)

    @property
    def async_read_url(self) -> str | None:
        return to_asyncpg_url(self.read_url) if self.read_url else None


@dataclass(frozen=True)
class MigrationStatus:
    authority: str = "knex"
    migrations_path: str = "packages/database/lib/migrations"
    message: str = MIGRATIONS_AUTHORITY


def build_database_url(
    *,
    user: str,
    password: str,
    host: str,
    port: int,
    database: str,
) -> str:
    return (
        f"postgres://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{quote(database, safe='')}"
    )


def parse_additional_schemas(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(schema for schema in (item.strip() for item in value.split(",")) if schema)


def to_asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def create_engine(settings: DatabaseSettings | None = None) -> AsyncEngine:
    resolved_settings = settings or DatabaseSettings.from_env()
    return create_async_engine(
        resolved_settings.async_url,
        connect_args=connect_args(resolved_settings),
        pool_size=resolved_settings.pool_max_size,
        max_overflow=0,
        pool_timeout=resolved_settings.statement_timeout_ms / 1000,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session, session.begin():
        yield session


def migration_status() -> MigrationStatus:
    return MigrationStatus()


def run_migrations() -> None:
    raise RuntimeError(MIGRATIONS_AUTHORITY)


async def check_database_health(session: AsyncSession) -> bool:
    result = await session.scalar(text("SELECT 1"))
    return bool(result == 1)


def connect_args(settings: DatabaseSettings) -> dict[str, Any]:
    args: dict[str, Any] = {
        "command_timeout": settings.statement_timeout_ms / 1000,
        "server_settings": {
            "application_name": settings.application_name,
            "statement_timeout": str(settings.statement_timeout_ms),
            "search_path": ",".join(settings.search_path),
        },
    }
    if settings.ssl_enabled:
        args["ssl"] = insecure_ssl_context()
    return args


def insecure_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context
