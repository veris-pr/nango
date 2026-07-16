from __future__ import annotations

from typing import Any, cast

from nango.orchestrator.events import InMemoryTaskEvents
from nango.orchestrator.models import (
    DequeueRequest,
    HeartbeatResponse,
    ImmediateTaskCreateRequest,
    ImmediateTaskCreateResponse,
    RecurringScheduleCreateRequest,
    RecurringScheduleCreateResponse,
    TaskTransitionRequest,
)
from nango.scheduler import (
    ImmediateTaskInput,
    RecurringScheduleInput,
    SchedulerEngine,
    ScheduleState,
    Task,
)

LONG_POLLING_TIMEOUT_SECONDS = 10.0


class DuplicateTaskNameError(ValueError):
    pass


class OrchestratorService:
    def __init__(
        self,
        scheduler: SchedulerEngine | None = None,
        events: InMemoryTaskEvents | None = None,
    ) -> None:
        self._scheduler = scheduler or SchedulerEngine()
        self._events = events or InMemoryTaskEvents()

    async def create_immediate(
        self,
        request: ImmediateTaskCreateRequest,
    ) -> ImmediateTaskCreateResponse:
        try:
            task = self._scheduler.immediate(
                ImmediateTaskInput(
                    name=request.name,
                    payload=_payload_json(request.args),
                    groupKey=request.group.key,
                    groupMaxConcurrency=request.group.max_concurrency,
                    retryMax=request.retry.max,
                    retryCount=request.retry.count,
                    ownerKey=request.owner_key or None,
                    createdToStartedTimeoutSecs=(
                        request.timeout_settings_in_secs.created_to_started
                    ),
                    startedToCompletedTimeoutSecs=(
                        request.timeout_settings_in_secs.started_to_completed
                    ),
                    heartbeatTimeoutSecs=request.timeout_settings_in_secs.heartbeat,
                )
            )
        except ValueError as exc:
            if "task name already exists" in str(exc):
                raise DuplicateTaskNameError(str(exc)) from exc
            raise

        await self._events.notify_task_created(task.group_key)
        return ImmediateTaskCreateResponse(taskId=task.id, retryKey=task.retry_key or "")

    async def create_recurring(
        self,
        request: RecurringScheduleCreateRequest,
    ) -> RecurringScheduleCreateResponse:
        schedule = self._scheduler.recurring(
            RecurringScheduleInput(
                name=request.name,
                state=ScheduleState(request.state),
                startsAt=request.starts_at,
                frequencyMs=request.frequency_ms,
                payload=_payload_json(request.args),
                groupKey=request.group.key,
                retryMax=request.retry.max,
                createdToStartedTimeoutSecs=request.timeout_settings_in_secs.created_to_started,
                startedToCompletedTimeoutSecs=(
                    request.timeout_settings_in_secs.started_to_completed
                ),
                heartbeatTimeoutSecs=request.timeout_settings_in_secs.heartbeat,
            )
        )
        return RecurringScheduleCreateResponse(scheduleId=schedule.id)

    async def dequeue(self, request: DequeueRequest) -> list[Task]:
        tasks = self._scheduler.dequeue(
            group_key_pattern=request.group_key_pattern,
            limit=request.limit,
        )
        if tasks or not request.long_polling:
            return tasks

        try:
            await self._events.wait_for_task_created(
                request.group_key_pattern,
                timeout_seconds=LONG_POLLING_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return []

        return self._scheduler.dequeue(
            group_key_pattern=request.group_key_pattern,
            limit=request.limit,
        )

    def heartbeat(self, task_id: str) -> HeartbeatResponse:
        task = self._scheduler.heartbeat(task_id)
        return HeartbeatResponse(taskId=task.id, lastHeartbeatAt=task.last_heartbeat_at)

    def transition_task(self, task_id: str, request: TaskTransitionRequest) -> Task:
        match request.state:
            case "SUCCEEDED":
                return self._scheduler.complete(task_id, request.output)
            case "FAILED":
                return self._scheduler.fail(task_id, request.output)
            case "CANCELLED":
                return self._scheduler.cancel(task_id, request.output)
            case _:
                raise ValueError(f"Unsupported task state: {request.state}")


def _payload_json(payload: object) -> object:
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        return cast(Any, payload).model_dump(mode="json", by_alias=True, exclude_none=True)
    return payload
