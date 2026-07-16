"""Records domain model.

Mirrors ``packages/records/lib/types.ts`` and
``packages/records/lib/models/records.ts``. Records are stored split across
``nango_records.records`` (metadata + data_hash) and
``nango_records.records_data`` (the actual JSON data).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

JsonObject = dict[str, Any]
RecordAction = Literal["ADDED", "UPDATED", "DELETED"]


@dataclass(frozen=True)
class RecordMetadata:
    first_seen_at: datetime
    last_modified_at: datetime
    last_action: RecordAction
    deleted_at: datetime | None
    cursor: str


@dataclass(frozen=True)
class Record:
    id: str
    external_id: str
    connection_id: int
    model: str
    data: JsonObject
    metadata: JsonObject = field(default_factory=dict)
    record_metadata: RecordMetadata | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    sync_id: str | None = None
    sync_job_id: int | None = None

    @property
    def deleted(self) -> bool:
        return self.deleted_at is not None


@dataclass(frozen=True)
class RecordInput:
    external_id: str
    connection_id: int
    model: str
    data: JsonObject
    metadata: JsonObject = field(default_factory=dict)
    sync_id: str | None = None
    sync_job_id: int | None = None


@dataclass(frozen=True)
class ListRecordsResult:
    records: list[Record]
    next_cursor: str | None = None


@dataclass(frozen=True)
class RecordCount:
    connection_id: int
    model: str
    count: int
    updated_at: datetime


@dataclass(frozen=True)
class RecordCheckpoint:
    connection_id: int
    model: str
    name: str
    cursor: str | None
    updated_at: datetime