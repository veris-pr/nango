"""Orchestrator service: task creation, dequeue, and transitions.

Mirrors ``packages/orchestrator/lib/routes/v1/`` handlers +
``packages/orchestrator/lib/clients/client.ts``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from nango_py.scheduler.domain.models import (
    ImmediateTaskInput,
    RecurringScheduleInput,
    Schedule,
    Task,
    TaskState,
)
from nango_py.scheduler.infrastructure.postgres_scheduler_repository import (
    PostgresSchedulerRepository,
)

JsonObject = dict[str, Any]
LONG_POLL_TIMEOUT_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 1.0


class DuplicateTaskNameError(ValueError):
    pass


@dataclass(frozen=True)
class ImmediateTaskResponse:
    task_id: str
    retry_key: str


@dataclass(frozen=True)
class RecurringScheduleResponse:
    schedule_id: str


@dataclass(frozen=True)
class HeartbeatResponse:
    task_id: str
    last_heartbeat_at: str


@dataclass(frozen=True)
class DequeueRequest:
    group_key_pattern: str
    limit: int
    long_polling: bool


class OrchestratorService:
    def __init__(self, repository: PostgresSchedulerRepository) -> None:
        self._repo = repository

    async def create_immediate(
        self, request: ImmediateTaskInput
    ) -> ImmediateTaskResponse:
        try:
            task = await self._repo.create_task(request)
        except Exception as exc:
            if "duplicate key" in str(exc).lower():
                raise DuplicateTaskNameError(str(exc)) from exc
            raise
        return ImmediateTaskResponse(
            task_id=task.id, retry_key=task.retry_key or ""
        )

    async def create_recurring(
        self, request: RecurringScheduleInput
    ) -> RecurringScheduleResponse:
        sched = await self._repo.create_schedule(request)
        return RecurringScheduleResponse(schedule_id=sched.id)

    async def dequeue(self, request: DequeueRequest) -> list[Task]:
        tasks = await self._repo.dequeue(
            group_key_pattern=request.group_key_pattern,
            limit=request.limit,
        )
        if tasks or not request.long_polling:
            return tasks

        deadline = asyncio.get_event_loop().time() + LONG_POLL_TIMEOUT_SECONDS
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            tasks = await self._repo.dequeue(
                group_key_pattern=request.group_key_pattern,
                limit=request.limit,
            )
            if tasks:
                return tasks
        return []

    async def heartbeat(self, task_id: str) -> HeartbeatResponse:
        task = await self._repo.heartbeat(task_id)
        return HeartbeatResponse(
            task_id=task.id,
            last_heartbeat_at=task.last_heartbeat_at.isoformat().replace("+00:00", "Z"),
        )

    async def transition(
        self, task_id: str, state: TaskState, output: JsonObject | None = None
    ) -> Task:
        return await self._repo.transition(task_id, state, output)

    async def get_task_output(self, task_id: str) -> JsonObject | None:
        task = await self._repo.get_task(task_id)
        return task.output if task else None

    async def search_tasks(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[Task]:
        return await self._repo.search_tasks(limit=limit, offset=offset)

    async def search_schedules(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[Schedule]:
        return await self._repo.search_schedules(limit=limit, offset=offset)

    async def run_schedule(self, schedule_id: str) -> Task:
        return await self._repo.run_schedule(schedule_id)

    async def update_recurring(
        self, *, schedule_id: str, name: str | None = None,
        interval_ms: int | None = None,
    ) -> Schedule:
        return await self._repo.update_schedule(
            schedule_id=schedule_id, name=name, interval_ms=interval_ms,
        )

    async def get_retry_output(self, retry_key: str) -> JsonObject | None:
        task = await self._repo.get_task_by_retry_key(retry_key)
        return task.output if task else None