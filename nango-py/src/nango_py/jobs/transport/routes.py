"""Jobs transport: callback routes for runner results + heartbeats.

The Node runner calls these endpoints to report task results and heartbeats:
- PUT /jobs/tasks/{taskId} → complete/fail task from runner result
- POST /jobs/tasks/{taskId}/heartbeat → forward heartbeat to orchestrator
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nango_py.jobs.application.processor import JobsProcessorService
from nango_py.jobs.domain.runner_boundary import RunnerTaskResult


class RunnerHeartbeatBody(BaseModel):
    task_id: str = Field(alias="taskId", min_length=1)


def create_jobs_callback_router(processor: JobsProcessorService) -> APIRouter:
    router = APIRouter(prefix="/jobs", tags=["jobs"])

    @router.put("/tasks/{task_id}")
    async def task_result(task_id: str, body: dict[str, Any]) -> JSONResponse:
        result = RunnerTaskResult.model_validate({**body, "taskId": task_id})
        task = await processor.complete_from_runner_result(result)
        if task is None:
            return JSONResponse({"status": "noop"}, status_code=200)
        return JSONResponse(
            {
                "id": task.id,
                "state": task.state,
                "terminated": task.terminated,
            }
        )

    @router.post("/tasks/{task_id}/heartbeat")
    async def heartbeat(task_id: str) -> JSONResponse:
        processor.heartbeat(task_id)
        return JSONResponse({"status": "ok"})

    return router