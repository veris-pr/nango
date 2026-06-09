from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response

from nango.persist.auth import persist_auth
from nango.persist.models import (
    CheckpointRequest,
    CheckpointResponse,
    DeleteRecordsRequest,
    DeleteRecordsResponse,
    ListPersistRecordsResponse,
    PersistAuthContext,
    PersistLogRequest,
    PersistNoopResponse,
    PersistRecordsRequest,
    PersistRecordsResponse,
)
from nango.persist.service import PersistService

PERSIST_V1_PREFIX = "/persist/v1"


def create_persist_router(service: PersistService | None = None) -> APIRouter:
    persist = service or PersistService()
    router = APIRouter(prefix=PERSIST_V1_PREFIX, tags=["persist"])

    @router.post(
        "/environment/{environment_id}/connection/{connection_id}/sync/{sync_id}/job/{sync_job_id}/records",
        response_model=PersistRecordsResponse,
    )
    async def post_records(
        connection_id: int,
        sync_id: str,
        sync_job_id: int,
        request: PersistRecordsRequest,
        auth: Annotated[PersistAuthContext, Depends(persist_auth)],
    ) -> PersistRecordsResponse:
        return await persist.persist_records(
            connection_id=connection_id,
            sync_id=sync_id,
            sync_job_id=sync_job_id,
            request=request,
            auth=auth,
            mode="save",
        )

    @router.put(
        "/environment/{environment_id}/connection/{connection_id}/sync/{sync_id}/job/{sync_job_id}/records",
        response_model=PersistRecordsResponse,
    )
    async def put_records(
        connection_id: int,
        sync_id: str,
        sync_job_id: int,
        request: PersistRecordsRequest,
        auth: Annotated[PersistAuthContext, Depends(persist_auth)],
    ) -> PersistRecordsResponse:
        return await persist.persist_records(
            connection_id=connection_id,
            sync_id=sync_id,
            sync_job_id=sync_job_id,
            request=request,
            auth=auth,
            mode="update",
        )

    @router.delete(
        "/environment/{environment_id}/connection/{connection_id}/sync/{sync_id}/job/{sync_job_id}/records",
        response_model=DeleteRecordsResponse,
    )
    async def delete_records(
        connection_id: int,
        request: DeleteRecordsRequest,
        auth: Annotated[PersistAuthContext, Depends(persist_auth)],
    ) -> DeleteRecordsResponse:
        return await persist.delete_records(connection_id=connection_id, request=request, auth=auth)

    @router.get(
        "/environment/{environment_id}/connection/{connection_id}/records",
        response_model=ListPersistRecordsResponse,
    )
    async def get_records(
        connection_id: int,
        auth: Annotated[PersistAuthContext, Depends(persist_auth)],
        model: str,
        limit: Annotated[int, Query(ge=1)] = 100,
        cursor: str | None = None,
        include_deleted: bool = Query(default=True, alias="includeDeleted"),
    ) -> ListPersistRecordsResponse:
        result = await persist.list_records(
            connection_id=connection_id,
            model=model,
            limit=limit,
            cursor=cursor,
            include_deleted=include_deleted,
        )
        return ListPersistRecordsResponse.model_validate(result.model_dump())

    @router.put(
        "/environment/{environment_id}/connection/{connection_id}/checkpoint",
        response_model=CheckpointResponse,
    )
    async def put_checkpoint(
        connection_id: int,
        request: CheckpointRequest,
        auth: Annotated[PersistAuthContext, Depends(persist_auth)],
    ) -> CheckpointResponse:
        return CheckpointResponse(
            checkpoint=await persist.save_checkpoint(
                connection_id=connection_id,
                request=request,
                auth=auth,
            )
        )

    @router.get(
        "/environment/{environment_id}/connection/{connection_id}/checkpoint",
        response_model=CheckpointResponse,
    )
    async def get_checkpoint(
        connection_id: int,
        auth: Annotated[PersistAuthContext, Depends(persist_auth)],
        model: str,
        key: str,
    ) -> CheckpointResponse | JSONResponse:
        checkpoint = await persist.get_checkpoint(
            connection_id=connection_id,
            model=model,
            key=key,
            auth=auth,
        )
        if checkpoint is None:
            return _api_error("checkpoint_not_found", "Checkpoint not found", status_code=404)
        return CheckpointResponse(checkpoint=checkpoint)

    @router.post("/environment/{environment_id}/log", status_code=204)
    async def post_log(
        request: PersistLogRequest,
        auth: Annotated[PersistAuthContext, Depends(persist_auth)],
    ) -> Response:
        await persist.write_log(request=request, auth=auth)
        return Response(status_code=204)

    @router.post("/daemon/prune", response_model=PersistNoopResponse)
    async def prune_records() -> PersistNoopResponse:
        return persist.prune_records()

    @router.post("/daemon/delete-expired", response_model=PersistNoopResponse)
    async def delete_expired_records() -> PersistNoopResponse:
        return persist.delete_expired_records()

    return router


def _api_error(code: str, message: str, *, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )
