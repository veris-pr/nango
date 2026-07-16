"""Harness smoke test: Knex migrations produce the auth tables Python will read."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

AUTH_TABLES = (
    "_nango_accounts",
    "_nango_environments",
    "api_secrets",
    "customer_keys",
    "customer_keys_relations",
)


async def test_migrations_create_auth_tables(clean_db: AsyncEngine) -> None:
    async with clean_db.connect() as conn:
        for table in AUTH_TABLES:
            qualified = f"nango.{table}"
            row = (
                await conn.execute(text("SELECT to_regclass(:rel)"), {"rel": qualified})
            ).scalar_one()
            assert row is not None, f"missing relation {qualified}"