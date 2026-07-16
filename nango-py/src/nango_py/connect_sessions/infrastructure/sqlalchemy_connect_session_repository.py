"""SQLAlchemy implementation of :class:`ConnectSessionRepository`.

Reads/writes ``connect_sessions`` table (migrated by Knex).
"""

from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.connect_sessions.domain.session import ConnectSession

_INSERT = text(
    """
    INSERT INTO connect_sessions
    (account_id, environment_id, allowed_integrations, integrations_config_defaults,
     end_user, tags, overrides)
    VALUES (:aid, :eid, :ai, :icd, :eu, :tags, :ovr)
    RETURNING *
    """
)
_GET = text(
    """
    SELECT * FROM connect_sessions
    WHERE id = :id AND account_id = :aid AND environment_id = :eid
    LIMIT 1
    """
)
_DELETE = text(
    """
    DELETE FROM connect_sessions
    WHERE id = :id AND account_id = :aid AND environment_id = :eid
    RETURNING id
    """
)


class SqlAlchemyConnectSessionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def create(
        self,
        *,
        account_id: int,
        environment_id: int,
        allowed_integrations: list[str] | None,
        integrations_config_defaults: dict[str, object] | None,
        end_user: dict[str, object] | None,
        tags: dict[str, str],
        overrides: dict[str, object] | None,
    ) -> ConnectSession:
        async with self._sf() as s:
            row = (
                await s.execute(
                    _INSERT,
                    {
                        "aid": account_id,
                        "eid": environment_id,
                        "ai": allowed_integrations,
                        "icd": json.dumps(integrations_config_defaults)
                        if integrations_config_defaults
                        else None,
                        "eu": json.dumps(end_user) if end_user else None,
                        "tags": json.dumps(tags),
                        "ovr": json.dumps(overrides) if overrides else None,
                    },
                )
            ).mappings().first()
            await s.commit()
        if row is None:
            raise RuntimeError("failed to create connect session")
        return _from_row(cast(dict[str, Any], row))

    async def get_by_id(
        self, *, id: int, account_id: int, environment_id: int
    ) -> ConnectSession | None:
        async with self._sf() as s:
            row = (
                await s.execute(_GET, {"id": id, "aid": account_id, "eid": environment_id})
            ).mappings().first()
        return _from_row(cast(dict[str, Any], row)) if row else None

    async def delete(self, *, id: int, account_id: int, environment_id: int) -> bool:
        async with self._sf() as s:
            row = (
                await s.execute(_DELETE, {"id": id, "aid": account_id, "eid": environment_id})
            ).mappings().first()
            await s.commit()
        return row is not None


def _from_row(row: dict[str, Any]) -> ConnectSession:
    return ConnectSession(
        id=row["id"],
        end_user_id=row.get("end_user_id"),
        account_id=row.get("account_id"),
        environment_id=row.get("environment_id"),
        allowed_integrations=tuple(row["allowed_integrations"])
        if row.get("allowed_integrations")
        else None,
        integrations_config_defaults=_json(row.get("integrations_config_defaults")),
        connection_id=row.get("connection_id"),
        operation_id=row.get("operation_id"),
        overrides=_json(row.get("overrides")),
        end_user=_json(row.get("end_user")),
        tags=_json(row.get("tags")) or {},
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _json(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None