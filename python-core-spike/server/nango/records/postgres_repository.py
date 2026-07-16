from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango.contracts.base import JsonObject
from nango.records.models import (
    ListRecordsResult,
    Record,
    RecordAction,
    RecordCheckpoint,
    RecordInput,
    RecordMetadata,
)

NIL_UUID = UUID(int=0)
CHECKPOINT_KEY_PREFIX = "persist"


class PostgresRecordsRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def upsert_records(
        self,
        *,
        environment_id: int,
        records: Iterable[RecordInput],
    ) -> list[Record]:
        return await self._write_records(
            environment_id=environment_id,
            records=records,
            merge_data=False,
        )

    async def update_records(
        self,
        *,
        environment_id: int,
        records: Iterable[RecordInput],
    ) -> list[Record]:
        return await self._write_records(
            environment_id=environment_id,
            records=records,
            merge_data=True,
        )

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
            raise ValueError("limit must be greater than 0")

        params: dict[str, object] = {
            "connection_id": connection_id,
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

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        f"""
                        SELECT
                            r.id,
                            r.external_id,
                            r.connection_id,
                            r.model,
                            r.created_at,
                            r.updated_at,
                            r.deleted_at,
                            r.sync_id,
                            r.sync_job_id,
                            d.data AS record_data,
                            CASE WHEN d.id IS NOT NULL THEN r.json ELSE NULL END AS metadata_json
                        FROM records AS r
                        LEFT JOIN records_data AS d
                            ON d.connection_id = r.connection_id
                           AND d.model = r.model
                           AND d.id = r.id
                        WHERE r.connection_id = :connection_id
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

        records = [
            _record_from_row(cast(Mapping[str, object], row))
            for row in rows[:limit]
        ]
        next_cursor = records[-1].record_metadata.cursor if len(rows) > limit and records else None
        return ListRecordsResult(records=records, next_cursor=next_cursor)

    async def delete_records(
        self,
        *,
        environment_id: int,
        connection_id: int,
        model: str,
        external_ids: Iterable[str] | None = None,
    ) -> int:
        del environment_id
        deleted_at = datetime.now(UTC)
        deleted = 0

        async with self._session_factory() as session:
            if external_ids is None:
                rows = (
                    await session.execute(
                        text(
                            """
                            UPDATE records
                            SET deleted_at = :deleted_at, updated_at = :deleted_at
                            WHERE connection_id = :connection_id
                              AND model = :model
                              AND deleted_at IS NULL
                            RETURNING id
                            """
                        ),
                        {
                            "connection_id": connection_id,
                            "model": model,
                            "deleted_at": deleted_at,
                        },
                    )
                ).mappings().all()
                deleted = len(rows)
            else:
                for external_id in external_ids:
                    rows = (
                        await session.execute(
                            text(
                                """
                                UPDATE records
                                SET deleted_at = :deleted_at, updated_at = :deleted_at
                                WHERE connection_id = :connection_id
                                  AND model = :model
                                  AND external_id = :external_id
                                  AND deleted_at IS NULL
                                RETURNING id
                                """
                            ),
                            {
                                "connection_id": connection_id,
                                "model": model,
                                "external_id": external_id,
                                "deleted_at": deleted_at,
                            },
                        )
                    ).mappings().all()
                    deleted += len(rows)
            await session.commit()

        return deleted

    async def save_checkpoint(
        self,
        *,
        environment_id: int,
        connection_id: int,
        model: str,
        name: str,
        cursor: str | None,
    ) -> RecordCheckpoint:
        updated_at = datetime.now(UTC)
        checkpoint_key = _checkpoint_key(model=model, name=name)
        checkpoint_json = json.dumps({"cursor": cursor})

        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        INSERT INTO checkpoints (
                            environment_id,
                            connection_id,
                            key,
                            checkpoint,
                            version,
                            created_at,
                            updated_at,
                            deleted_at
                        )
                        VALUES (
                            :environment_id,
                            :connection_id,
                            :checkpoint_key,
                            CAST(:checkpoint_json AS jsonb),
                            1,
                            :updated_at,
                            :updated_at,
                            NULL
                        )
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
                        "environment_id": environment_id,
                        "connection_id": connection_id,
                        "checkpoint_key": checkpoint_key,
                        "checkpoint_json": checkpoint_json,
                        "updated_at": updated_at,
                    },
                )
            ).mappings().first()
            await session.commit()

        if row is None:
            raise RuntimeError("Failed to save checkpoint")
        checkpoint_row = cast(Mapping[str, object], row)
        checkpoint_payload = _json_object(checkpoint_row.get("checkpoint"))
        return RecordCheckpoint(
            connection_id=connection_id,
            model=model,
            name=name,
            cursor=_optional_str_from_json(checkpoint_payload, "cursor"),
            updated_at=_required_datetime(checkpoint_row, "updated_at"),
        )

    async def get_checkpoint(
        self,
        *,
        environment_id: int,
        connection_id: int,
        model: str,
        name: str,
    ) -> RecordCheckpoint | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT checkpoint, updated_at
                        FROM checkpoints
                        WHERE environment_id = :environment_id
                          AND connection_id = :connection_id
                          AND key = :checkpoint_key
                          AND deleted_at IS NULL
                        LIMIT 1
                        """
                    ),
                    {
                        "environment_id": environment_id,
                        "connection_id": connection_id,
                        "checkpoint_key": _checkpoint_key(model=model, name=name),
                    },
                )
            ).mappings().first()

        if row is None:
            return None
        checkpoint_row = cast(Mapping[str, object], row)
        checkpoint_payload = _json_object(checkpoint_row.get("checkpoint"))
        return RecordCheckpoint(
            connection_id=connection_id,
            model=model,
            name=name,
            cursor=_optional_str_from_json(checkpoint_payload, "cursor"),
            updated_at=_required_datetime(checkpoint_row, "updated_at"),
        )

    async def _write_records(
        self,
        *,
        environment_id: int,
        records: Iterable[RecordInput],
        merge_data: bool,
    ) -> list[Record]:
        del environment_id
        persisted: list[Record] = []

        async with self._session_factory() as session:
            for record in records:
                persisted.append(
                    await self._write_record(
                        session,
                        record=record,
                        merge_data=merge_data,
                    )
                )
            await session.commit()

        return persisted

    async def _write_record(
        self,
        session: AsyncSession,
        *,
        record: RecordInput,
        merge_data: bool,
    ) -> Record:
        existing = await self._get_existing_record(
            session,
            connection_id=record.connection_id,
            model=record.model,
            external_id=record.external_id,
        )
        now = datetime.now(UTC)
        metadata = record.metadata
        data = (
            _merge_json(existing.data, record.data)
            if merge_data and existing is not None
            else record.data
        )
        record_id = existing.id if existing is not None else _stable_record_id(
            connection_id=record.connection_id,
            model=record.model,
            external_id=record.external_id,
        )

        if existing is not None:
            has_changed = (
                existing.data != data
                or existing.metadata != metadata
                or existing.deleted
                or existing.sync_id != record.sync_id
                or existing.sync_job_id != record.sync_job_id
            )
            if not has_changed:
                return existing

            await session.execute(
                text(
                    """
                    UPDATE records
                    SET
                        json = CASE
                            WHEN :metadata_json IS NULL THEN NULL
                            ELSE CAST(:metadata_json AS jsonb)
                        END,
                        data_hash = :data_hash,
                        updated_at = :updated_at,
                        deleted_at = NULL,
                        sync_id = :sync_id,
                        sync_job_id = :sync_job_id
                    WHERE connection_id = :connection_id
                      AND model = :model
                      AND external_id = :external_id
                    """
                ),
                {
                    "metadata_json": _json_payload(metadata),
                    "data_hash": _data_hash(data),
                    "updated_at": now,
                    "sync_id": record.sync_id,
                    "sync_job_id": record.sync_job_id,
                    "connection_id": record.connection_id,
                    "model": record.model,
                    "external_id": record.external_id,
                },
            )
        else:
            await session.execute(
                text(
                    """
                    INSERT INTO records (
                        id,
                        external_id,
                        json,
                        data_hash,
                        connection_id,
                        model,
                        created_at,
                        updated_at,
                        deleted_at,
                        sync_id,
                        sync_job_id
                    )
                    VALUES (
                        :id,
                        :external_id,
                        CASE
                            WHEN :metadata_json IS NULL THEN NULL
                            ELSE CAST(:metadata_json AS jsonb)
                        END,
                        :data_hash,
                        :connection_id,
                        :model,
                        :created_at,
                        :updated_at,
                        NULL,
                        :sync_id,
                        :sync_job_id
                    )
                    """
                ),
                {
                    "id": record_id,
                    "external_id": record.external_id,
                    "metadata_json": _json_payload(metadata),
                    "data_hash": _data_hash(data),
                    "connection_id": record.connection_id,
                    "model": record.model,
                    "created_at": now,
                    "updated_at": now,
                    "sync_id": record.sync_id,
                    "sync_job_id": record.sync_job_id,
                },
            )

        await session.execute(
            text(
                """
                INSERT INTO records_data (id, connection_id, model, data)
                VALUES (:id, :connection_id, :model, CAST(:data_json AS jsonb))
                ON CONFLICT (connection_id, model, id)
                DO UPDATE SET data = EXCLUDED.data
                """
            ),
            {
                "id": record_id,
                "connection_id": record.connection_id,
                "model": record.model,
                "data_json": _json_payload(data),
            },
        )

        return Record(
            id=record_id,
            external_id=record.external_id,
            connection_id=record.connection_id,
            model=record.model,
            data=data,
            metadata=metadata,
            _nango_metadata=_record_metadata(
                created_at=existing.created_at if existing is not None else now,
                updated_at=now,
                deleted_at=None,
                record_id=record_id,
                last_action="UPDATED" if existing is not None else "ADDED",
            ),
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
            deleted_at=None,
            sync_id=record.sync_id,
            sync_job_id=record.sync_job_id,
        )

    async def _get_existing_record(
        self,
        session: AsyncSession,
        *,
        connection_id: int,
        model: str,
        external_id: str,
    ) -> Record | None:
        row = (
            await session.execute(
                text(
                    """
                    SELECT
                        r.id,
                        r.external_id,
                        r.connection_id,
                        r.model,
                        r.created_at,
                        r.updated_at,
                        r.deleted_at,
                        r.sync_id,
                        r.sync_job_id,
                        r.json AS legacy_json,
                        d.data AS record_data,
                        CASE WHEN d.id IS NOT NULL THEN r.json ELSE NULL END AS metadata_json
                    FROM records AS r
                    LEFT JOIN records_data AS d
                        ON d.connection_id = r.connection_id
                       AND d.model = r.model
                       AND d.id = r.id
                    WHERE r.connection_id = :connection_id
                      AND r.model = :model
                      AND r.external_id = :external_id
                    LIMIT 1
                    """
                ),
                {
                    "connection_id": connection_id,
                    "model": model,
                    "external_id": external_id,
                },
            )
        ).mappings().first()
        if row is None:
            return None
        return _record_from_row(cast(Mapping[str, object], row))


def _record_from_row(row: Mapping[str, object]) -> Record:
    created_at = _required_datetime(row, "created_at")
    updated_at = _required_datetime(row, "updated_at")
    deleted_at = _optional_datetime(row, "deleted_at")
    record_id = _required_str(row, "id")
    data = _json_object(row.get("record_data"))
    if not data:
        data = _json_object(row.get("legacy_json"))
    metadata = _json_object(row.get("metadata_json"))

    return Record(
        id=record_id,
        external_id=_required_str(row, "external_id"),
        connection_id=_required_int(row, "connection_id"),
        model=_required_str(row, "model"),
        data=data,
        metadata=metadata,
        _nango_metadata=_record_metadata(
            created_at=created_at,
            updated_at=updated_at,
            deleted_at=deleted_at,
            record_id=record_id,
            last_action=_last_action(
                created_at=created_at,
                updated_at=updated_at,
                deleted_at=deleted_at,
            ),
        ),
        created_at=created_at,
        updated_at=updated_at,
        deleted_at=deleted_at,
        sync_id=_optional_str(row, "sync_id"),
        sync_job_id=_optional_int(row, "sync_job_id"),
    )


def _record_metadata(
    *,
    created_at: datetime,
    updated_at: datetime,
    deleted_at: datetime | None,
    record_id: str,
    last_action: RecordAction,
) -> RecordMetadata:
    return RecordMetadata(
        first_seen_at=created_at,
        last_modified_at=updated_at,
        last_action=last_action,
        deleted_at=deleted_at,
        cursor=_cursor_for(updated_at, record_id),
    )


def _last_action(
    *,
    created_at: datetime,
    updated_at: datetime,
    deleted_at: datetime | None,
) -> RecordAction:
    if deleted_at is not None:
        return "DELETED"
    if updated_at > created_at:
        return "UPDATED"
    return "ADDED"


def _stable_record_id(*, connection_id: int, model: str, external_id: str) -> str:
    namespace = uuid5(NIL_UUID, f"{connection_id}{model}")
    return str(uuid5(namespace, f"{connection_id}{model}{external_id}"))


def _data_hash(data: JsonObject) -> str:
    payload = json.dumps(data, separators=(",", ":"))
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _checkpoint_key(*, model: str, name: str) -> str:
    return f"{CHECKPOINT_KEY_PREFIX}:{model}:{name}"


def _cursor_for(updated_at: datetime, record_id: str) -> str:
    payload = [updated_at.isoformat(), record_id]
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    value = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("invalid record cursor")
    return str(value[0]), str(value[1])


def _json_payload(value: JsonObject) -> str | None:
    if not value:
        return None
    return json.dumps(value, separators=(",", ":"))


def _json_object(value: object) -> JsonObject:
    if isinstance(value, dict):
        return cast(JsonObject, value)
    return {}


def _merge_json(existing: JsonObject, incoming: JsonObject) -> JsonObject:
    merged = dict(existing)
    merged.update(incoming)
    return merged


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int):
        raise RuntimeError(f"Expected integer column: {key}")
    return value


def _optional_int(row: Mapping[str, object], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise RuntimeError(f"Expected integer column: {key}")
    return value


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise RuntimeError(f"Expected string column: {key}")
    return value


def _optional_str(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"Expected string column: {key}")
    return value


def _optional_str_from_json(value: JsonObject, key: str) -> str | None:
    item = value.get(key)
    return item if isinstance(item, str) else None


def _required_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row.get(key)
    if not isinstance(value, datetime):
        raise RuntimeError(f"Expected datetime column: {key}")
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _optional_datetime(row: Mapping[str, object], key: str) -> datetime | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise RuntimeError(f"Expected datetime column: {key}")
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
