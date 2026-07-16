"""FastAPI router for the persist boundary.

Mirrors ``packages/persist/lib/server.ts`` route registration:
- POST/PUT/DELETE records (save/update/delete)
- GET records (list with cursor pagination)
- PUT/GET checkpoint
- POST log (deferred — no-op)
- Daemon no-ops (prune, delete-expired)

Auth: internal secret key (Bearer token via ``api_auth``) + environment_id
match check.

Authoritative behavior:
``packages/persist/lib/routes/environment/environmentId/connection/connectionId/sync/syncId/job/jobId/``
``postRecords.ts``, ``putRecords.ts``, ``deleteRecords.ts``,
``getRecords.ts``, ``checkpoint/putCheckpoint.ts``, ``checkpoint/getCheckpoint.ts``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.transport.dependencies import api_auth
from nango_py.records.application.gateway import RecordsRepository
from nango_py.records.domain.record import RecordInput
from nango_py.shared.errors import ApiError

JsonObject = dict[str, Any]


class PersistRecordInput(BaseModel):
    id: str
    data: JsonObject
    metadata: JsonObject = Field(default_factory=dict)


class PersistRecordsBody(BaseModel):
    model_config = {"extra": "allow"}
    model: str
    records: list[PersistRecordInput]
    activity_log_id: str | None = Field(default=None, alias="activityLogId")
    merging: JsonObject = Field(default_factory=dict)


class DeleteRecordsBody(BaseModel):
    model_config = {"extra": "allow"}
    model: str
    external_ids: list[str] | None = Field(default=None, alias="externalIds")
    records: list[PersistRecordInput] = Field(default_factory=list)
    activity_log_id: str | None = Field(default=None, alias="activityLogId")


class CheckpointBody(BaseModel):
    model_config = {"extra": "allow"}
    model: str
    key: str
    cursor: str | None = None


def create_persist_router(records_repository: RecordsRepository) -> APIRouter:
    router = APIRouter(tags=["persist"])

    @router.post(
        "/environment/{environment_id}/connection/{connection_id}/sync/{sync_id}/job/{sync_job_id}/records"
    )
    async def post_records(
        environment_id: int,
        connection_id: int,
        sync_id: str,
        sync_job_id: int,
        body: PersistRecordsBody,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_env(auth, environment_id)
        records = [
            RecordInput(
                external_id=r.id,
                connection_id=connection_id,
                model=body.model,
                data=r.data,
                metadata=r.metadata,
                sync_id=sync_id,
                sync_job_id=sync_job_id,
            )
            for r in body.records
        ]
        persisted = await records_repository.upsert_records(
            environment_id=environment_id, records=records
        )
        return JSONResponse(
            {"records": len(persisted), "nextMerging": body.merging}
        )

    @router.put(
        "/environment/{environment_id}/connection/{connection_id}/sync/{sync_id}/job/{sync_job_id}/records"
    )
    async def put_records(
        environment_id: int,
        connection_id: int,
        sync_id: str,
        sync_job_id: int,
        body: PersistRecordsBody,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_env(auth, environment_id)
        records = [
            RecordInput(
                external_id=r.id,
                connection_id=connection_id,
                model=body.model,
                data=r.data,
                metadata=r.metadata,
                sync_id=sync_id,
                sync_job_id=sync_job_id,
            )
            for r in body.records
        ]
        persisted = await records_repository.update_records(
            environment_id=environment_id, records=records
        )
        return JSONResponse(
            {"records": len(persisted), "nextMerging": body.merging}
        )

    @router.delete(
        "/environment/{environment_id}/connection/{connection_id}/sync/{sync_id}/job/{sync_job_id}/records"
    )
    async def delete_records(
        environment_id: int,
        connection_id: int,
        sync_id: str,
        sync_job_id: int,
        body: DeleteRecordsBody,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_env(auth, environment_id)
        external_ids = body.external_ids
        if external_ids is None and body.records:
            external_ids = [r.id for r in body.records]
        deleted = await records_repository.delete_records(
            environment_id=environment_id,
            connection_id=connection_id,
            model=body.model,
            external_ids=external_ids,
        )
        return JSONResponse({"deleted": deleted})

    @router.get(
        "/environment/{environment_id}/connection/{connection_id}/records"
    )
    async def get_records(
        environment_id: int,
        connection_id: int,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        model: str = Query(...),
        limit: int = Query(default=100, ge=1),
        cursor: str | None = Query(default=None),
        include_deleted: bool = Query(default=True, alias="includeDeleted"),
    ) -> JSONResponse:
        _check_env(auth, environment_id)
        result = await records_repository.list_records(
            connection_id=connection_id,
            model=model,
            limit=limit,
            cursor=cursor,
            include_deleted=include_deleted,
        )
        return JSONResponse({
            "records": [
                {
                    "id": r.id,
                    "external_id": r.external_id,
                    "connection_id": r.connection_id,
                    "model": r.model,
                    "data": r.data,
                    "metadata": r.metadata,
                    "created_at": _iso(r.created_at),
                    "updated_at": _iso(r.updated_at),
                    "deleted_at": _iso(r.deleted_at),
                    "sync_id": r.sync_id,
                    "sync_job_id": r.sync_job_id,
                }
                for r in result.records
            ],
            "next_cursor": result.next_cursor,
        })

    @router.put(
        "/environment/{environment_id}/connection/{connection_id}/checkpoint"
    )
    async def put_checkpoint(
        environment_id: int,
        connection_id: int,
        body: CheckpointBody,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_env(auth, environment_id)
        checkpoint = await records_repository.save_checkpoint(
            environment_id=environment_id,
            connection_id=connection_id,
            model=body.model,
            name=body.key,
            cursor=body.cursor,
        )
        return JSONResponse(
            {
                "checkpoint": {
                    "connection_id": checkpoint.connection_id,
                    "model": checkpoint.model,
                    "name": checkpoint.name,
                    "cursor": checkpoint.cursor,
                    "updated_at": _iso(checkpoint.updated_at),
                }
            }
        )

    @router.get(
        "/environment/{environment_id}/connection/{connection_id}/checkpoint"
    )
    async def get_checkpoint_route(
        environment_id: int,
        connection_id: int,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        model: str = Query(...),
        key: str = Query(...),
    ) -> JSONResponse:
        _check_env(auth, environment_id)
        checkpoint = await records_repository.get_checkpoint(
            environment_id=environment_id,
            connection_id=connection_id,
            model=model,
            name=key,
        )
        if checkpoint is None:
            return JSONResponse(
                {"error": {"code": "checkpoint_not_found", "message": "Checkpoint not found"}},
                status_code=404,
            )
        return JSONResponse(
            {
                "checkpoint": {
                    "connection_id": checkpoint.connection_id,
                    "model": checkpoint.model,
                    "name": checkpoint.name,
                    "cursor": checkpoint.cursor,
                    "updated_at": _iso(checkpoint.updated_at),
                }
            }
        )

    @router.post("/environment/{environment_id}/log", status_code=204)
    async def post_log(
        environment_id: int,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> Response:
        _check_env(auth, environment_id)
        return Response(status_code=204)

    @router.post("/daemon/prune")
    async def prune() -> JSONResponse:
        return JSONResponse({"status": "noop"})

    @router.post("/daemon/delete-expired")
    async def delete_expired() -> JSONResponse:
        return JSONResponse({"status": "noop"})

    @router.delete(
        "/environment/{environment_id}/connection/{connection_id}/checkpoint"
    )
    async def delete_checkpoint_route(
        environment_id: int,
        connection_id: int,
        body: CheckpointBody,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_env(auth, environment_id)
        await records_repository.delete_checkpoint(
            environment_id=environment_id,
            connection_id=connection_id,
            model=body.model,
            name=body.key,
        )
        return JSONResponse({"success": True})

    @router.get(
        "/environment/{environment_id}/connection/{connection_id}/cursor"
    )
    async def get_cursor_route(
        environment_id: int,
        connection_id: int,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        model: str = Query(...),
        offset: str | None = Query(default=None),
    ) -> JSONResponse:
        _check_env(auth, environment_id)
        checkpoint = await records_repository.get_checkpoint(
            environment_id=environment_id,
            connection_id=connection_id,
            model=model,
            name="cursor",
        )
        if checkpoint is None:
            return JSONResponse(
                {"error": {"code": "cursor_not_found", "message": "Cursor not found"}},
                status_code=404,
            )
        return JSONResponse({"cursor": checkpoint.cursor})

    @router.delete(
        "/environment/{environment_id}/connection/{connection_id}"
        "/sync/{sync_id}/job/{sync_job_id}/outdated-records"
    )
    async def delete_outdated_records(
        environment_id: int,
        connection_id: int,
        sync_id: str,
        sync_job_id: int,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        model: str = Query(...),
        batch_size: int = Query(default=1000, alias="batchSize"),
    ) -> JSONResponse:
        _check_env(auth, environment_id)
        deleted = await records_repository.delete_outdated(
            environment_id=environment_id,
            connection_id=connection_id,
            model=model,
            sync_id=sync_id,
            sync_job_id=sync_job_id,
        )
        return JSONResponse({"deleted": deleted})

    @router.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return router


def _check_env(auth: AuthenticatedContext, environment_id: int) -> None:
    if auth.environment.id != environment_id:
        raise _env_mismatch()


def _env_mismatch() -> ApiError:
    class _Mismatch(ApiError):
        status = 401
        code = "unauthorized"
        message = "Unauthorized: Matching environment not found"

    return _Mismatch()


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    result = dt.isoformat().replace("+00:00", "Z")
    return str(result)


__all__: list[Any] = []