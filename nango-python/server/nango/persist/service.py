from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from nango.logs import InMemoryLogsRepository, MessageLogEntry
from nango.persist.models import (
    CheckpointRequest,
    DeleteRecordsRequest,
    DeleteRecordsResponse,
    PersistAuthContext,
    PersistLogRequest,
    PersistMode,
    PersistNoopResponse,
    PersistRecordsRequest,
    PersistRecordsResponse,
)
from nango.records import (
    InMemoryRecordsRepository,
    ListRecordsResult,
    RecordCheckpoint,
    RecordInput,
)


class PersistService:
    def __init__(
        self,
        records_repository: InMemoryRecordsRepository | None = None,
        logs_repository: InMemoryLogsRepository | None = None,
    ) -> None:
        self._records = records_repository or InMemoryRecordsRepository()
        self._logs = logs_repository or InMemoryLogsRepository()

    def persist_records(
        self,
        *,
        connection_id: int,
        sync_id: str,
        sync_job_id: int,
        request: PersistRecordsRequest,
        auth: PersistAuthContext,
        mode: PersistMode,
    ) -> PersistRecordsResponse:
        records = [
            RecordInput(
                external_id=record.id,
                connection_id=connection_id,
                model=request.model,
                data=record.data,
                metadata=record.metadata,
                sync_id=sync_id,
                sync_job_id=sync_job_id,
            )
            for record in request.records
        ]
        if mode == "update":
            persisted = self._records.update_records(records)
        else:
            persisted = self._records.upsert_records(records)

        self._write_activity_log(
            activity_log_id=request.activity_log_id,
            auth=auth,
            message=f"Persisted {len(persisted)} {request.model} record(s)",
            meta={"model": request.model, "mode": mode},
        )
        return PersistRecordsResponse(records=len(persisted), nextMerging=request.merging)

    def list_records(
        self,
        *,
        connection_id: int,
        model: str,
        limit: int,
        cursor: str | None,
        include_deleted: bool,
    ) -> ListRecordsResult:
        return self._records.list_records(
            connection_id=connection_id,
            model=model,
            limit=limit,
            cursor=cursor,
            include_deleted=include_deleted,
        )

    def delete_records(
        self,
        *,
        connection_id: int,
        request: DeleteRecordsRequest,
        auth: PersistAuthContext,
    ) -> DeleteRecordsResponse:
        external_ids = request.external_ids
        if external_ids is None and request.records:
            external_ids = [record.id for record in request.records]

        deleted = self._records.delete_records(
            connection_id=connection_id,
            model=request.model,
            external_ids=external_ids,
        )
        self._write_activity_log(
            activity_log_id=request.activity_log_id,
            auth=auth,
            message=f"Deleted {deleted} {request.model} record(s)",
            meta={"model": request.model},
        )
        return DeleteRecordsResponse(deleted=deleted)

    def save_checkpoint(
        self,
        *,
        connection_id: int,
        request: CheckpointRequest,
    ) -> RecordCheckpoint:
        return self._records.save_checkpoint(
            connection_id=connection_id,
            model=request.model,
            name=request.key,
            cursor=request.cursor,
        )

    def get_checkpoint(
        self,
        *,
        connection_id: int,
        model: str,
        key: str,
    ) -> RecordCheckpoint | None:
        return self._records.get_checkpoint(connection_id=connection_id, model=model, name=key)

    def write_log(self, *, request: PersistLogRequest, auth: PersistAuthContext) -> None:
        self._write_activity_log(
            activity_log_id=request.activity_log_id,
            auth=auth,
            message=request.message,
            meta=request.meta,
            level=request.level,
            created_at=request.created_at,
        )

    def prune_records(self) -> PersistNoopResponse:
        """Placeholder for the TS auto-pruning daemon; no production loop is started."""
        return PersistNoopResponse()

    def delete_expired_records(self) -> PersistNoopResponse:
        """Placeholder for the TS auto-deleting daemon; no production loop is started."""
        return PersistNoopResponse()

    def _write_activity_log(
        self,
        *,
        activity_log_id: str | None,
        auth: PersistAuthContext,
        message: str,
        meta: dict[str, object] | None,
        level: str = "info",
        created_at: datetime | None = None,
    ) -> None:
        if not activity_log_id:
            return

        entry = MessageLogEntry.model_validate(
            {
                "id": str(uuid4()),
                "parentId": activity_log_id,
                "accountId": auth.account_id,
                "message": message,
                "level": level,
                "type": "log",
                "createdAt": created_at or datetime.now(UTC),
                "meta": meta,
            }
        )
        self._logs.create_message(entry)
