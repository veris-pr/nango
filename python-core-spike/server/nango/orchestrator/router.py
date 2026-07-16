from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from nango.orchestrator.models import (
    DequeueRequest,
    HeartbeatResponse,
    ImmediateTaskCreateRequest,
    ImmediateTaskCreateResponse,
    RecurringScheduleCreateRequest,
    RecurringScheduleCreateResponse,
    TaskTransitionRequest,
)
from nango.orchestrator.service import DuplicateTaskNameError, OrchestratorService
from nango.scheduler import Task

ORCHESTRATOR_V1_PREFIX = "/orchestrator/v1"


def create_orchestrator_router(service: OrchestratorService | None = None) -> APIRouter:
    orchestrator = service or OrchestratorService()
    router = APIRouter(prefix=ORCHESTRATOR_V1_PREFIX, tags=["orchestrator"])

    @router.post("/immediate", response_model=ImmediateTaskCreateResponse)
    async def create_immediate(
        request: ImmediateTaskCreateRequest,
    ) -> ImmediateTaskCreateResponse | JSONResponse:
        try:
            return await orchestrator.create_immediate(request)
        except DuplicateTaskNameError as exc:
            return _api_error("duplicate_task_name", str(exc), status_code=409)
        except ValueError as exc:
            return _api_error("immediate_failed", str(exc), status_code=500)

    @router.post("/recurring", response_model=RecurringScheduleCreateResponse)
    async def create_recurring(
        request: RecurringScheduleCreateRequest,
    ) -> RecurringScheduleCreateResponse | JSONResponse:
        try:
            return await orchestrator.create_recurring(request)
        except ValueError as exc:
            return _api_error("recurring_failed", str(exc), status_code=500)

    @router.post("/dequeue", response_model=list[Task])
    async def dequeue(request: DequeueRequest) -> list[Task] | JSONResponse:
        try:
            return await orchestrator.dequeue(request)
        except ValueError as exc:
            return _api_error("dequeue_failed", str(exc), status_code=500)

    @router.post("/tasks/{task_id}/heartbeat", response_model=HeartbeatResponse)
    async def heartbeat(task_id: str) -> HeartbeatResponse | JSONResponse:
        try:
            return orchestrator.heartbeat(task_id)
        except ValueError as exc:
            return _api_error("post_heartbeat_failed", str(exc), status_code=400)

    @router.put("/tasks/{task_id}", response_model=Task)
    async def transition_task(
        task_id: str,
        request: TaskTransitionRequest,
    ) -> Task | JSONResponse:
        try:
            return orchestrator.transition_task(task_id, request)
        except ValueError as exc:
            return _api_error("put_task_failed", str(exc), status_code=400)

    return router


def _api_error(code: str, message: str, *, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )
