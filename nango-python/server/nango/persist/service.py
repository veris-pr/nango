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
    PostgresRecordsRepository,
    RecordCheckpoint,
    RecordInput,
)

RecordsRepository = InMemoryRecordsRepository | PostgresRecordsRepository


class PersistService:
    def __init__(
        self,
        records_repository: RecordsRepository | None = None,
        logs_repository: InMemoryLogsRepository | None = None,
    ) -> None:
        self.records_repository: RecordsRepository = (
            records_repository or InMemoryRecordsRepository()
        )
        self._logs = logs_repository or InMemoryLogsRepository()

    async def persist_records(
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

        if isinstance(self.records_repository, PostgresRecordsRepository):
            if mode == "update":
                persisted = await self.records_repository.update_records(
                    environment_id=auth.environment_id,
                    records=records,
                )
            else:
                persisted = await self.records_repository.upsert_records(
                    environment_id=auth.environment_id,
                    records=records,
                )
        elif mode == "update":
            persisted = self.records_repository.update_records(records)
        else:
            persisted = self.records_repository.upsert_records(records)

        if request.activity_log_id:
            await self.write_log(
                request=PersistLogRequest(
                    activityLogId=request.activity_log_id,
                    message=f"Persisted {len(persisted)} {request.model} record(s)",
                    level="info",
                    createdAt=datetime.now(UTC),
                    meta={"model": request.model, "mode": mode},
                ),
                auth=auth,
            )
        return PersistRecordsResponse(records=len(persisted), nextMerging=request.merging)

    async def list_records(
        self,
        *,
        connection_id: int,
        model: str,
        limit: int,
        cursor: str | None,
        include_deleted: bool,
    ) -> ListRecordsResult:
        if isinstance(self.records_repository, PostgresRecordsRepository):
            return await self.records_repository.list_records(
                connection_id=connection_id,
                model=model,
                limit=limit,
                cursor=cursor,
                include_deleted=include_deleted,
            )
        return self.records_repository.list_records(
            connection_id=connection_id,
            model=model,
            limit=limit,
            cursor=cursor,
            include_deleted=include_deleted,
        )

    async def delete_records(
        self,
        *,
        connection_id: int,
        request: DeleteRecordsRequest,
        auth: PersistAuthContext,
    ) -> DeleteRecordsResponse:
        external_ids = request.external_ids
        if external_ids is None and request.records:
            external_ids = [record.id for record in request.records]

        if isinstance(self.records_repository, PostgresRecordsRepository):
            deleted = await self.records_repository.delete_records(
                environment_id=auth.environment_id,
                connection_id=connection_id,
                model=request.model,
                external_ids=external_ids,
            )
        else:
            deleted = self.records_repository.delete_records(
                connection_id=connection_id,
                model=request.model,
                external_ids=external_ids,
            )
        if request.activity_log_id:
            await self.write_log(
                request=PersistLogRequest(
                    activityLogId=request.activity_log_id,
                    message=f"Deleted {deleted} {request.model} record(s)",
                    level="info",
                    createdAt=datetime.now(UTC),
                    meta={"model": request.model},
                ),
                auth=auth,
            )
        return DeleteRecordsResponse(deleted=deleted)

    async def save_checkpoint(
        self,
        *,
        connection_id: int,
        request: CheckpointRequest,
        auth: PersistAuthContext,
    ) -> RecordCheckpoint:
        if isinstance(self.records_repository, PostgresRecordsRepository):
            return await self.records_repository.save_checkpoint(
                environment_id=auth.environment_id,
                connection_id=connection_id,
                model=request.model,
                name=request.key,
                cursor=request.cursor,
            )
        return self.records_repository.save_checkpoint(
            connection_id=connection_id,
            model=request.model,
            name=request.key,
            cursor=request.cursor,
        )

    async def get_checkpoint(
        self,
        *,
        connection_id: int,
        model: str,
        key: str,
        auth: PersistAuthContext,
    ) -> RecordCheckpoint | None:
        if isinstance(self.records_repository, PostgresRecordsRepository):
            return await self.records_repository.get_checkpoint(
                environment_id=auth.environment_id,
                connection_id=connection_id,
                model=model,
                name=key,
            )
        return self.records_repository.get_checkpoint(
            connection_id=connection_id,
            model=model,
            name=key,
        )

    async def write_log(self, *, request: PersistLogRequest, auth: PersistAuthContext) -> None:
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
