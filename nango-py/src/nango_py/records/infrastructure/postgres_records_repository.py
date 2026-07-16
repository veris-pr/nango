"""Postgres implementation of :class:`RecordsRepository`.

Operates against the ``nango_records`` schema (records, records_data) and the
``nango`` schema (checkpoints — already migrated by the app DB migrations).

Mirrors ``packages/records/lib/models/records.ts``:
- Deterministic IDs via uuid5 (connection_id + model + external_id)
- MD5 data hash for change detection
- Split storage: records (metadata) + records_data (actual JSON)
- Soft delete (set deleted_at)
- Cursor pagination by (updated_at, id)
- Checkpoints in the app DB (nango.checkpoints)

Deferred: record encryption, batch CTE upserts, advisory locking,
record_counts table, merging strategies (ignore_if_modified_after_cursor),
size accounting, daemon pruning.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.records.domain.record import (
    ListRecordsResult,
    Record,
    RecordCheckpoint,
    RecordInput,
)

NIL_UUID = UUID(int=0)
CHECKPOINT_KEY_PREFIX = "persist"


class PostgresRecordsRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._sf = session_factory

    async def upsert_records(
        self, *, environment_id: int, records: Iterable[RecordInput]
    ) -> list[Record]:
        return await self._write_records(
            environment_id=environment_id, records=records, merge_data=False
        )

    async def update_records(
        self, *, environment_id: int, records: Iterable[RecordInput]
    ) -> list[Record]:
        return await self._write_records(
            environment_id=environment_id, records=records, merge_data=True
        )

    async def delete_records(
        self,
        *,
        environment_id: int,
        connection_id: int,
        model: str,
        external_ids: Iterable[str] | None = None,
    ) -> int:
        del environment_id
        now = datetime.now(UTC)
        deleted = 0

        async with self._sf() as session:
            if external_ids is None:
                result = await session.execute(
                    text(
                        """
                        UPDATE nango_records.records
                        SET deleted_at = :now, updated_at = :now
                        WHERE connection_id = :cid AND model = :model
                          AND deleted_at IS NULL
                        RETURNING id
                        """
                    ),
                    {"cid": connection_id, "model": model, "now": now},
                )
                deleted = len(result.fetchall())
            else:
                for ext_id in external_ids:
                    result = await session.execute(
                        text(
                            """
                            UPDATE nango_records.records
                            SET deleted_at = :now, updated_at = :now
                            WHERE connection_id = :cid AND model = :model
                              AND external_id = :eid AND deleted_at IS NULL
                            RETURNING id
                            """
                        ),
                        {"cid": connection_id, "model": model, "eid": ext_id, "now": now},
                    )
                    deleted += len(result.fetchall())
            await session.commit()

        return deleted

    async def list_records(
        self,
        *,
        connection_id: int,
        model: str,
        limit: int = 100,
        cursor: str | None = None,
        include_deleted: bool = True,
    ) -> ListRecordsResult:
        if limit < 1:
            raise ValueError("limit must be > 0")

        params: dict[str, Any] = {
            "cid": connection_id,
            "model": model,
            "include_deleted": include_deleted,
            "limit": limit + 1,
        }
        cursor_clause = ""
        if cursor is not None:
            cursor_sort, cursor_id = _decode_cursor(cursor)
            params["cursor_sort"] = datetime.fromisoformat(cursor_sort)
            params["cursor_id"] = cursor_id
            cursor_clause = "AND (r.updated_at, r.id) > (:cursor_sort, :cursor_id)"

        async with self._sf() as session:
            rows = (
                await session.execute(
                    text(
                        f"""
                        SELECT r.id, r.external_id, r.connection_id, r.model,
                               r.created_at, r.updated_at, r.deleted_at,
                               r.sync_id, r.sync_job_id,
                               d.data AS record_data,
                               r.json AS metadata_json
                        FROM nango_records.records AS r
                        LEFT JOIN nango_records.records_data AS d
                            ON d.connection_id = r.connection_id
                           AND d.model = r.model
                           AND d.id = r.id
                        WHERE r.connection_id = :cid
                          AND r.model = :model
                          AND (:include_deleted OR r.deleted_at IS NULL)
                          {cursor_clause}
                        ORDER BY r.updated_at ASC, r.id ASC
                        LIMIT :limit
                        """
                    ),
                    params,
                )
            ).mappings().all()

        records = [_record_from_row(cast(dict[str, Any], row)) for row in rows[:limit]]
        next_cursor = None
        if len(rows) > limit and records:
            last = records[-1]
            if last.record_metadata is not None:
                next_cursor = last.record_metadata.cursor
            elif last.updated_at is not None:
                next_cursor = _cursor_for(last.updated_at, last.id)
        return ListRecordsResult(records=records, next_cursor=next_cursor)

    async def count_records(self, *, connection_id: int, model: str) -> int:
        async with self._sf() as session:
            result = await session.scalar(
                text(
                    """
                    SELECT COUNT(*) FROM nango_records.records
                    WHERE connection_id = :cid AND model = :model
                      AND deleted_at IS NULL
                    """
                ),
                {"cid": connection_id, "model": model},
            )
        return int(result or 0)

    async def save_checkpoint(
        self,
        *,
        environment_id: int,
        connection_id: int,
        model: str,
        name: str,
        cursor: str | None,
    ) -> RecordCheckpoint:
        key = _checkpoint_key(model=model, name=name)
        checkpoint_json = json.dumps({"cursor": cursor})
        now = datetime.now(UTC)

        async with self._sf() as session:
            row = (
                await session.execute(
                    text(
                        """
                        INSERT INTO checkpoints
                            (environment_id, connection_id, key, checkpoint, version,
                             created_at, updated_at, deleted_at)
                        VALUES (:eid, :cid, :key, CAST(:ckpt AS jsonb), 1, :now, :now, NULL)
                        ON CONFLICT (environment_id, connection_id, key)
                        DO UPDATE SET
                            checkpoint = EXCLUDED.checkpoint,
                            version = checkpoints.version + 1,
                            deleted_at = NULL,
                            updated_at = EXCLUDED.updated_at
                        RETURNING checkpoint, updated_at
                        """
                    ),
                    {
                        "eid": environment_id,
                        "cid": connection_id,
                        "key": key,
                        "ckpt": checkpoint_json,
                        "now": now,
                    },
                )
            ).mappings().first()
            await session.commit()

        if row is None:
            raise RuntimeError("Failed to save checkpoint")
        row_dict = cast(dict[str, Any], row)
        ckpt_payload = _json_object(row_dict.get("checkpoint"))
        return RecordCheckpoint(
            connection_id=connection_id,
            model=model,
            name=name,
            cursor=_optional_str_from_json(ckpt_payload, "cursor"),
            updated_at=_required_datetime(row_dict, "updated_at"),
        )

    async def get_checkpoint(
        self,
        *,
        environment_id: int,
        connection_id: int,
        model: str,
        name: str,
    ) -> RecordCheckpoint | None:
        async with self._sf() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT checkpoint, updated_at
                        FROM checkpoints
                        WHERE environment_id = :eid
                          AND connection_id = :cid
                          AND key = :key
                          AND deleted_at IS NULL
                        LIMIT 1
                        """
                    ),
                    {
                        "eid": environment_id,
                        "cid": connection_id,
                        "key": _checkpoint_key(model=model, name=name),
                    },
                )
            ).mappings().first()

        if row is None:
            return None
        row_dict = cast(dict[str, Any], row)
        ckpt_payload = _json_object(row_dict.get("checkpoint"))
        return RecordCheckpoint(
            connection_id=connection_id,
            model=model,
            name=name,
            cursor=_optional_str_from_json(ckpt_payload, "cursor"),
            updated_at=_required_datetime(row_dict, "updated_at"),
        )

    async def delete_checkpoint(
        self,
        *,
        environment_id: int,
        connection_id: int,
        model: str,
        name: str,
    ) -> None:
        async with self._sf() as session:
            await session.execute(
                text(
                    """
                    UPDATE checkpoints
                    SET deleted_at = NOW()
                    WHERE environment_id = :eid
                      AND connection_id = :cid
                      AND key = :key
                      AND deleted_at IS NULL
                    """
                ),
                {
                    "eid": environment_id,
                    "cid": connection_id,
                    "key": _checkpoint_key(model=model, name=name),
                },
            )
            await session.commit()

    async def delete_outdated(
        self,
        *,
        environment_id: int,
        connection_id: int,
        model: str,
        sync_id: str,
        sync_job_id: int,
    ) -> int:
        """Soft-delete records not present in the latest sync job batch."""
        async with self._sf() as session:
            result = await session.execute(
                text(
                    """
                    UPDATE nango_records.records
                    SET deleted_at = NOW(),
                        last_action = 'DELETED'
                    WHERE connection_id = :cid
                      AND model = :model
                      AND deleted_at IS NULL
                      AND id NOT IN (
                        SELECT record_id FROM nango_records.record_data
                        WHERE sync_id = :sid
                          AND sync_job_id = :sjid
                      )
                    RETURNING id
                    """
                ),
                {
                    "cid": connection_id,
                    "model": model,
                    "sid": sync_id,
                    "sjid": sync_job_id,
                },
            )
            await session.commit()
            deleted = cast(int, getattr(result, "rowcount", 0) or 0)
            return deleted

    async def _write_records(
        self,
        *,
        environment_id: int,
        records: Iterable[RecordInput],
        merge_data: bool,
    ) -> list[Record]:
        del environment_id
        persisted: list[Record] = []

        async with self._sf() as session:
            for record in records:
                persisted.append(
                    await self._write_one(session, record=record, merge_data=merge_data)
                )
            await session.commit()

        return persisted

    async def _write_one(
        self,
        session: AsyncSession,
        *,
        record: RecordInput,
        merge_data: bool,
    ) -> Record:
        existing = await self._get_existing(session, record=record)

        now = datetime.now(UTC)
        data = (
            _merge_json(existing.data, record.data)
            if merge_data and existing is not None
            else record.data
        )
        record_id = (
            existing.id
            if existing is not None
            else _stable_record_id(
                connection_id=record.connection_id,
                model=record.model,
                external_id=record.external_id,
            )
        )

        if existing is not None:
            has_changed = (
                existing.data != data
                or existing.metadata_json != record.metadata
                or existing.deleted
                or existing.sync_id != record.sync_id
                or existing.sync_job_id != record.sync_job_id
            )
            if not has_changed:
                return existing.to_record()

            await session.execute(
                text(
                    """
                    UPDATE nango_records.records
                    SET json = CAST(:meta AS jsonb),
                        data_hash = :hash, updated_at = :now,
                        deleted_at = NULL, sync_id = :sid, sync_job_id = :sjid
                    WHERE connection_id = :cid AND model = :model
                      AND external_id = :eid
                    """
                ),
                {
                    "meta": _json_payload(record.metadata),
                    "hash": _data_hash(data),
                    "now": now,
                    "sid": record.sync_id,
                    "sjid": record.sync_job_id,
                    "cid": record.connection_id,
                    "model": record.model,
                    "eid": record.external_id,
                },
            )
        else:
            await session.execute(
                text(
                    """
                    INSERT INTO nango_records.records
                        (id, external_id, json, data_hash, connection_id, model,
                         created_at, updated_at, sync_id, sync_job_id)
                    VALUES (:id, :eid,
                        CAST(:meta AS jsonb),
                        :hash, :cid, :model, :now, :now, :sid, :sjid)
                    """
                ),
                {
                    "id": record_id,
                    "eid": record.external_id,
                    "meta": _json_payload(record.metadata),
                    "hash": _data_hash(data),
                    "cid": record.connection_id,
                    "model": record.model,
                    "now": now,
                    "sid": record.sync_id,
                    "sjid": record.sync_job_id,
                },
            )

        await session.execute(
            text(
                """
                INSERT INTO nango_records.records_data (id, connection_id, model, data)
                VALUES (:id, :cid, :model, CAST(:data AS jsonb))
                ON CONFLICT (connection_id, model, id)
                DO UPDATE SET data = EXCLUDED.data
                """
            ),
            {
                "id": record_id,
                "cid": record.connection_id,
                "model": record.model,
                "data": _json_payload(data),
            },
        )

        created_at = existing.created_at if existing is not None else now
        return Record(
            id=record_id,
            external_id=record.external_id,
            connection_id=record.connection_id,
            model=record.model,
            data=data,
            metadata=record.metadata,
            created_at=created_at,
            updated_at=now,
            deleted_at=None,
            sync_id=record.sync_id,
            sync_job_id=record.sync_job_id,
        )

    async def _get_existing(
        self, session: AsyncSession, *, record: RecordInput
    ) -> _ExistingRecord | None:
        row = (
            await session.execute(
                text(
                    """
                    SELECT r.id, r.created_at, r.updated_at, r.deleted_at,
                           r.sync_id, r.sync_job_id, r.json AS metadata_json,
                           d.data AS record_data
                    FROM nango_records.records AS r
                    LEFT JOIN nango_records.records_data AS d
                        ON d.connection_id = r.connection_id
                       AND d.model = r.model
                       AND d.id = r.id
                    WHERE r.connection_id = :cid AND r.model = :model
                      AND r.external_id = :eid
                    LIMIT 1
                    """
                ),
                {
                    "cid": record.connection_id,
                    "model": record.model,
                    "eid": record.external_id,
                },
            )
        ).mappings().first()

        if row is None:
            return None
        row_dict = cast(dict[str, Any], row)
        return _ExistingRecord(
            id=row_dict["id"],
            created_at=row_dict["created_at"],
            updated_at=row_dict["updated_at"],
            deleted=row_dict["deleted_at"] is not None,
            sync_id=row_dict.get("sync_id"),
            sync_job_id=row_dict.get("sync_job_id"),
            metadata_json=row_dict.get("metadata_json"),
            data=_json_object(row_dict.get("record_data")),
        )


class _ExistingRecord:
    __slots__ = (
        "id", "created_at", "updated_at", "deleted", "sync_id",
        "sync_job_id", "metadata_json", "data",
    )

    def __init__(
        self,
        *,
        id: str,
        created_at: datetime,
        updated_at: datetime,
        deleted: bool,
        sync_id: str | None,
        sync_job_id: int | None,
        metadata_json: dict[str, Any] | None,
        data: dict[str, Any],
    ) -> None:
        self.id = str(id)
        self.created_at = created_at
        self.updated_at = updated_at
        self.deleted = deleted
        self.sync_id = sync_id
        self.sync_job_id = sync_job_id
        self.metadata_json = metadata_json
        self.data = data

    def to_record(self) -> Record:
        return Record(
            id=self.id,
            external_id="",
            connection_id=0,
            model="",
            data=self.data,
            metadata=self.metadata_json or {},
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=None,
            sync_id=self.sync_id,
            sync_job_id=self.sync_job_id,
        )


def _stable_record_id(*, connection_id: int, model: str, external_id: str) -> str:
    namespace = uuid5(NIL_UUID, f"{connection_id}{model}")
    return str(uuid5(namespace, f"{connection_id}{model}{external_id}"))


def _data_hash(data: dict[str, Any]) -> str:
    return hashlib.md5(json.dumps(data, separators=(",", ":")).encode()).hexdigest()


def _checkpoint_key(*, model: str, name: str) -> str:
    return f"{CHECKPOINT_KEY_PREFIX}:{model}:{name}"


def _cursor_for(updated_at: datetime, record_id: str) -> str:
    return base64.urlsafe_b64encode(
        json.dumps([updated_at.isoformat(), record_id]).encode()
    ).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    value = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("invalid record cursor")
    return str(value[0]), str(value[1])


def _json_payload(value: dict[str, Any]) -> str:
    if not value:
        return "null"
    return json.dumps(value, separators=(",", ":"))


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast("dict[str, Any]", value)
    return {}


def _merge_json(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged.update(incoming)
    return merged


def _optional_str_from_json(value: dict[str, Any], key: str) -> str | None:
    item = value.get(key)
    return item if isinstance(item, str) else None


def _required_datetime(row: dict[str, Any], key: str) -> datetime:
    value = row[key]
    if not isinstance(value, datetime):
        raise RuntimeError(f"expected datetime column: {key}")
    return value


def _record_from_row(row: dict[str, Any]) -> Record:
    created_at = _required_datetime(row, "created_at")
    updated_at = _required_datetime(row, "updated_at")
    deleted_at = row.get("deleted_at")
    record_id = str(row["id"])
    data = _json_object(row.get("record_data"))
    metadata = _json_object(row.get("metadata_json"))

    return Record(
        id=record_id,
        external_id=row["external_id"],
        connection_id=row["connection_id"],
        model=row["model"],
        data=data,
        metadata=metadata,
        created_at=created_at,
        updated_at=updated_at,
        deleted_at=deleted_at if isinstance(deleted_at, datetime) else None,
        sync_id=str(row["sync_id"]) if row.get("sync_id") else None,
        sync_job_id=row.get("sync_job_id"),
    )