"""Orchestrator transport: routes for /v1/immediate, /v1/recurring, /v1/dequeue, /v1/tasks.

No auth (mirrors the TS orchestrator which has no auth middleware — TODO).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nango_py.scheduler.application.orchestrator_service import (
    DequeueRequest,
    DuplicateTaskNameError,
    OrchestratorService,
)

JsonObject = dict[str, Any]


class TaskGroupRequest(BaseModel):
    key: str = Field(min_length=1)
    max_concurrency: int = Field(alias="maxConcurrency", ge=0)


class RetryRequest(BaseModel):
    count: int = Field(ge=0)
    max: int = Field(ge=0)


class TimeoutSettings(BaseModel):
    created_to_started: int = Field(alias="createdToStarted", gt=0)
    started_to_completed: int = Field(alias="startedToCompleted", gt=0)
    heartbeat: int = Field(gt=0)


class ImmediateRequest(BaseModel):
    model_config = {"extra": "allow"}
    name: str = Field(min_length=1)
    owner_key: str = Field(default="", alias="ownerKey")
    group: TaskGroupRequest
    retry: RetryRequest
    timeout_settings_in_secs: TimeoutSettings = Field(alias="timeoutSettingsInSecs")
    args: JsonObject


class RecurringRequest(BaseModel):
    model_config = {"extra": "allow"}
    name: str = Field(min_length=1)
    state: str = "STARTED"
    starts_at: str = Field(alias="startsAt")
    frequency_ms: int = Field(alias="frequencyMs", gt=0)
    group: TaskGroupRequest
    retry: dict[str, int] = Field(default_factory=lambda: {"max": 0})
    timeout_settings_in_secs: TimeoutSettings = Field(alias="timeoutSettingsInSecs")
    args: JsonObject


class DequeueBody(BaseModel):
    group_key_pattern: str = Field(alias="groupKeyPattern", min_length=1)
    limit: int = Field(gt=0)
    long_polling: bool = Field(alias="longPolling")


class TransitionBody(BaseModel):
    output: Any = None
    state: str
    next_execution_in_ms: int | None = Field(default=None, alias="nextExecutionInMs", ge=0)


class SearchBody(BaseModel):
    model_config = {"extra": "allow"}
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class ScheduleRunBody(BaseModel):
    schedule_id: str = Field(alias="scheduleId")


class UpdateRecurringBody(BaseModel):
    model_config = {"extra": "allow"}
    schedule_id: str = Field(alias="scheduleId")
    name: str | None = None
    interval_ms: int | None = Field(default=None, alias="intervalMs", ge=1)


def create_orchestrator_router(service: OrchestratorService) -> APIRouter:
    router = APIRouter(prefix="/orchestrator/v1", tags=["orchestrator"])

    @router.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @router.post("/immediate")
    async def create_immediate(body: ImmediateRequest) -> JSONResponse:

        try:
            result = await service.create_immediate(
                _to_immediate_input(body)
            )
        except DuplicateTaskNameError as exc:
            return JSONResponse(
                {"error": {"code": "duplicate_task_name", "message": str(exc)}},
                status_code=409,
            )
        except ValueError as exc:
            return JSONResponse(
                {"error": {"code": "immediate_failed", "message": str(exc)}},
                status_code=500,
            )
        return JSONResponse(
            {"taskId": result.task_id, "retryKey": result.retry_key}
        )

    @router.post("/recurring")
    async def create_recurring(body: RecurringRequest) -> JSONResponse:
        try:
            result = await service.create_recurring(
                _to_recurring_input(body)
            )
        except ValueError as exc:
            return JSONResponse(
                {"error": {"code": "recurring_failed", "message": str(exc)}},
                status_code=500,
            )
        return JSONResponse({"scheduleId": result.schedule_id})

    @router.post("/dequeue")
    async def dequeue(body: DequeueBody) -> JSONResponse:
        try:
            tasks = await service.dequeue(
                DequeueRequest(
                    group_key_pattern=body.group_key_pattern,
                    limit=body.limit,
                    long_polling=body.long_polling,
                )
            )
        except ValueError as exc:
            return JSONResponse(
                {"error": {"code": "dequeue_failed", "message": str(exc)}},
                status_code=500,
            )
        return JSONResponse([_task_to_dict(t) for t in tasks])

    @router.post("/tasks/{task_id}/heartbeat")
    async def heartbeat(task_id: str) -> JSONResponse:
        try:
            result = await service.heartbeat(task_id)
        except ValueError as exc:
            return JSONResponse(
                {"error": {"code": "post_heartbeat_failed", "message": str(exc)}},
                status_code=400,
            )
        return JSONResponse(
            {"taskId": result.task_id, "lastHeartbeatAt": result.last_heartbeat_at}
        )

    @router.put("/tasks/{task_id}")
    async def transition(task_id: str, body: TransitionBody) -> JSONResponse:
        try:
            task = await service.transition(
                task_id, body.state,  # type: ignore[arg-type]
                body.output,
            )
        except ValueError as exc:
            return JSONResponse(
                {"error": {"code": "put_task_failed", "message": str(exc)}},
                status_code=400,
            )
        return JSONResponse(_task_to_dict(task))

    @router.get("/tasks/{task_id}/output")
    async def get_task_output(task_id: str) -> JSONResponse:
        try:
            output = await service.get_task_output(task_id)
        except ValueError as exc:
            return JSONResponse(
                {"error": {"code": "not_found", "message": str(exc)}},
                status_code=404,
            )
        return JSONResponse({"output": output})

    @router.post("/tasks/search")
    async def search_tasks(body: SearchBody) -> JSONResponse:
        tasks = await service.search_tasks(
            limit=body.limit, offset=body.offset,
        )
        return JSONResponse({
            "tasks": [_task_to_dict(t) for t in tasks],
            "total": len(tasks),
        })

    @router.post("/schedules/search")
    async def search_schedules(body: SearchBody) -> JSONResponse:
        schedules = await service.search_schedules(
            limit=body.limit, offset=body.offset,
        )
        return JSONResponse({
            "schedules": [_schedule_to_dict(s) for s in schedules],
            "total": len(schedules),
        })

    @router.post("/schedules/run")
    async def run_schedule(body: ScheduleRunBody) -> JSONResponse:
        try:
            task = await service.run_schedule(body.schedule_id)
        except ValueError as exc:
            return JSONResponse(
                {"error": {"code": "schedule_not_found", "message": str(exc)}},
                status_code=404,
            )
        return JSONResponse(_task_to_dict(task))

    @router.put("/recurring")
    async def update_recurring(body: UpdateRecurringBody) -> JSONResponse:
        try:
            schedule = await service.update_recurring(
                schedule_id=body.schedule_id,
                name=body.name,
                interval_ms=body.interval_ms,
            )
        except ValueError as exc:
            return JSONResponse(
                {"error": {"code": "update_failed", "message": str(exc)}},
                status_code=400,
            )
        return JSONResponse(_schedule_to_dict(schedule))

    @router.get("/retries/{retry_key}/output")
    async def get_retry_output(retry_key: str) -> JSONResponse:
        try:
            output = await service.get_retry_output(retry_key)
        except ValueError as exc:
            return JSONResponse(
                {"error": {"code": "not_found", "message": str(exc)}},
                status_code=404,
            )
        return JSONResponse({"output": output})

    return router


def _to_immediate_input(body: ImmediateRequest) -> Any:
    from datetime import UTC, datetime

    from nango_py.scheduler.domain.models import ImmediateTaskInput

    return ImmediateTaskInput(
        name=body.name,
        payload=body.args,
        group_key=body.group.key,
        group_max_concurrency=body.group.max_concurrency,
        retry_max=body.retry.max,
        retry_count=body.retry.count,
        retry_key=None,
        owner_key=body.owner_key or None,
        starts_after=datetime.now(UTC),
        created_to_started_timeout_secs=body.timeout_settings_in_secs.created_to_started,
        started_to_completed_timeout_secs=body.timeout_settings_in_secs.started_to_completed,
        heartbeat_timeout_secs=body.timeout_settings_in_secs.heartbeat,
    )


def _to_recurring_input(body: RecurringRequest) -> Any:
    from datetime import datetime

    from nango_py.scheduler.domain.models import RecurringScheduleInput

    starts_at = datetime.fromisoformat(body.starts_at.replace("Z", "+00:00"))
    return RecurringScheduleInput(
        name=body.name,
        state=body.state,  # type: ignore[arg-type]
        starts_at=starts_at,
        frequency_ms=body.frequency_ms,
        payload=body.args,
        group_key=body.group.key,
        retry_max=body.retry.get("max", 0),
        created_to_started_timeout_secs=body.timeout_settings_in_secs.created_to_started,
        started_to_completed_timeout_secs=body.timeout_settings_in_secs.started_to_completed,
        heartbeat_timeout_secs=body.timeout_settings_in_secs.heartbeat,
    )


def _task_to_dict(task: Any) -> dict[str, Any]:
    return {
        "id": task.id,
        "name": task.name,
        "payload": task.payload,
        "groupKey": task.group_key,
        "groupMaxConcurrency": task.group_max_concurrency,
        "retryMax": task.retry_max,
        "retryCount": task.retry_count,
        "retryKey": task.retry_key,
        "ownerKey": task.owner_key,
        "startsAfter": task.starts_after.isoformat().replace("+00:00", "Z"),
        "createdToStartedTimeoutSecs": task.created_to_started_timeout_secs,
        "startedToCompletedTimeoutSecs": task.started_to_completed_timeout_secs,
        "heartbeatTimeoutSecs": task.heartbeat_timeout_secs,
        "createdAt": task.created_at.isoformat().replace("+00:00", "Z"),
        "state": task.state,
        "lastStateTransitionAt": task.last_state_transition_at.isoformat().replace("+00:00", "Z"),
        "lastHeartbeatAt": task.last_heartbeat_at.isoformat().replace("+00:00", "Z"),
        "output": task.output,
        "terminated": task.terminated,
        "scheduleId": task.schedule_id,
    }


def _schedule_to_dict(schedule: Any) -> dict[str, Any]:
    return {
        "scheduleId": schedule.schedule_id,
        "name": schedule.name,
        "state": schedule.state,
        "intervalMs": schedule.interval_ms,
        "retryMax": schedule.retry_max,
    }


__all__: list[Any] = []