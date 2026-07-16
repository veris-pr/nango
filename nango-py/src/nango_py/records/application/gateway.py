"""Records repository protocol.

Operations mirror ``packages/records/lib/models/records.ts``:
upsert (deterministic uuid5 IDs + MD5 data hash + INSERT ON CONFLICT),
update (merge), delete (soft), list (cursor pagination), count, checkpoints.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from nango_py.records.domain.record import (
    ListRecordsResult,
    Record,
    RecordCheckpoint,
    RecordInput,
)


class RecordsRepository(Protocol):
    async def upsert_records(
        self, *, environment_id: int, records: Iterable[RecordInput]
    ) -> list[Record]: ...

    async def update_records(
        self, *, environment_id: int, records: Iterable[RecordInput]
    ) -> list[Record]: ...

    async def delete_records(
        self, *, environment_id: int, connection_id: int, model: str,
        external_ids: Iterable[str] | None = None,
    ) -> int: ...

    async def list_records(
        self, *, connection_id: int, model: str, limit: int = 100,
        cursor: str | None = None, include_deleted: bool = True,
    ) -> ListRecordsResult: ...

    async def count_records(
        self, *, connection_id: int, model: str
    ) -> int: ...

    async def save_checkpoint(
        self, *, environment_id: int, connection_id: int, model: str,
        name: str, cursor: str | None,
    ) -> RecordCheckpoint: ...

    async def get_checkpoint(
        self, *, environment_id: int, connection_id: int, model: str, name: str,
    ) -> RecordCheckpoint | None: ...

    async def delete_checkpoint(
        self, *, environment_id: int, connection_id: int, model: str, name: str,
    ) -> None: ...

    async def delete_outdated(
        self, *, environment_id: int, connection_id: int, model: str,
        sync_id: str, sync_job_id: int,
    ) -> int: ...