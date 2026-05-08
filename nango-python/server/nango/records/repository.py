from __future__ import annotations

import base64
import json
from collections.abc import Callable, Iterable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from nango.records.models import (
    ListRecordsResult,
    Record,
    RecordAction,
    RecordCheckpoint,
    RecordCount,
    RecordInput,
    RecordMetadata,
)

RecordKey = tuple[int, str, str]
CheckpointKey = tuple[int, str, str]


class InMemoryRecordsRepository:
    """In-memory records contract foundation.

    Existing partitioned Postgres records migrations remain the source of truth for
    production storage. This repository is intentionally a deterministic test double
    until a real adapter targets that schema.
    """

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._records: dict[RecordKey, Record] = {}
        self._checkpoints: dict[CheckpointKey, RecordCheckpoint] = {}

    def upsert_records(self, records: Iterable[RecordInput]) -> list[Record]:
        return [self._upsert_record(record, merge_data=False) for record in records]

    def update_records(self, records: Iterable[RecordInput]) -> list[Record]:
        return [self._upsert_record(record, merge_data=True) for record in records]

    def list_records(
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

        records = [
            record
            for record in self._ordered_records()
            if record.connection_id == connection_id
            and record.model == model
            and (include_deleted or not record.deleted)
        ]
        start = self._cursor_start(records, cursor)
        page_with_extra = records[start : start + limit + 1]
        page = page_with_extra[:limit]
        next_cursor = page[-1].record_metadata.cursor if len(page_with_extra) > limit else None
        return ListRecordsResult(records=page, next_cursor=next_cursor)

    def delete_records(
        self,
        *,
        connection_id: int,
        model: str,
        external_ids: Iterable[str] | None = None,
    ) -> int:
        target_ids = set(external_ids) if external_ids is not None else None
        deleted = 0
        for key, record in list(self._records.items()):
            if record.connection_id != connection_id or record.model != model:
                continue
            if target_ids is not None and record.external_id not in target_ids:
                continue
            if record.deleted:
                continue

            now = self._now()
            updated = self._with_metadata(
                record.model_copy(update={"deleted_at": now, "updated_at": now}),
                last_action="DELETED",
            )
            self._records[key] = updated
            deleted += 1
        return deleted

    def count_records(self, *, connection_id: int, model: str) -> RecordCount:
        count = sum(
            1
            for record in self._records.values()
            if (
                record.connection_id == connection_id
                and record.model == model
                and not record.deleted
            )
        )
        return RecordCount(
            connection_id=connection_id,
            model=model,
            count=count,
            updated_at=self._now(),
        )

    def save_checkpoint(
        self,
        *,
        connection_id: int,
        model: str,
        name: str,
        cursor: str | None,
    ) -> RecordCheckpoint:
        checkpoint = RecordCheckpoint(
            connection_id=connection_id,
            model=model,
            name=name,
            cursor=cursor,
            updated_at=self._now(),
        )
        self._checkpoints[(connection_id, model, name)] = checkpoint
        return checkpoint

    def get_checkpoint(
        self,
        *,
        connection_id: int,
        model: str,
        name: str,
    ) -> RecordCheckpoint | None:
        return self._checkpoints.get((connection_id, model, name))

    def _upsert_record(self, incoming: RecordInput, *, merge_data: bool) -> Record:
        key = (incoming.connection_id, incoming.model, incoming.external_id)
        existing = self._records.get(key)
        now = self._now()

        if existing is None:
            record = Record(
                id=incoming.id or str(uuid4()),
                external_id=incoming.external_id,
                connection_id=incoming.connection_id,
                model=incoming.model,
                data=self._copy_json(incoming.data),
                metadata=self._copy_json(incoming.metadata),
                _nango_metadata=self._metadata(
                    first_seen_at=now,
                    last_modified_at=now,
                    last_action="ADDED",
                    deleted_at=None,
                    cursor="",
                    record_id=incoming.id or "",
                ),
                created_at=now,
                updated_at=now,
                sync_id=incoming.sync_id,
                sync_job_id=incoming.sync_job_id,
            )
            record = self._with_metadata(record, last_action="ADDED")
            self._records[key] = record
            return record

        data = self._merged_data(existing.data, incoming.data) if merge_data else incoming.data
        has_changed = (
            existing.data != data
            or existing.metadata != incoming.metadata
            or existing.deleted
            or existing.sync_id != incoming.sync_id
            or existing.sync_job_id != incoming.sync_job_id
        )
        if not has_changed:
            return existing

        updated = existing.model_copy(
            update={
                "data": self._copy_json(data),
                "metadata": self._copy_json(incoming.metadata),
                "updated_at": now,
                "deleted_at": None,
                "sync_id": incoming.sync_id,
                "sync_job_id": incoming.sync_job_id,
            }
        )
        updated = self._with_metadata(updated, last_action="UPDATED")
        self._records[key] = updated
        return updated

    def _with_metadata(self, record: Record, *, last_action: RecordAction) -> Record:
        metadata = self._metadata(
            first_seen_at=record.created_at,
            last_modified_at=record.updated_at,
            last_action=last_action,
            deleted_at=record.deleted_at,
            cursor=self._cursor_for(record.updated_at, record.id),
            record_id=record.id,
        )
        return record.model_copy(update={"record_metadata": metadata})

    def _metadata(
        self,
        *,
        first_seen_at: datetime,
        last_modified_at: datetime,
        last_action: RecordAction,
        deleted_at: datetime | None,
        cursor: str,
        record_id: str,
    ) -> RecordMetadata:
        if not cursor and record_id:
            cursor = self._cursor_for(last_modified_at, record_id)
        return RecordMetadata(
            first_seen_at=first_seen_at,
            last_modified_at=last_modified_at,
            last_action=last_action,
            deleted_at=deleted_at,
            cursor=cursor,
        )

    def _ordered_records(self) -> list[Record]:
        return sorted(self._records.values(), key=lambda record: (record.updated_at, record.id))

    def _cursor_start(self, records: list[Record], cursor: str | None) -> int:
        if cursor is None:
            return 0

        cursor_key = self._decode_cursor(cursor)
        for index, record in enumerate(records):
            if (record.updated_at.isoformat(), record.id) > cursor_key:
                return index
        return len(records)

    def _cursor_for(self, updated_at: datetime, record_id: str) -> str:
        payload = [updated_at.isoformat(), record_id]
        return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()

    def _decode_cursor(self, cursor: str) -> tuple[str, str]:
        value = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("invalid record cursor")
        return (str(value[0]), str(value[1]))

    def _now(self) -> datetime:
        return self._clock()

    def _merged_data(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = self._copy_json(existing)
        merged.update(self._copy_json(incoming))
        return merged

    def _copy_json(self, value: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(value)
