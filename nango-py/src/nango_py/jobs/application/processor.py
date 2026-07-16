"""Jobs processor: dequeue from orchestrator, dispatch to runner or webhook.

Mirrors ``packages/jobs/lib/processor/processor.ts`` +
``packages/jobs/lib/processor/handler.ts``.

Phase 8 scope: sync/action dispatch to Node runner via HTTP, webhook dispatch
to the webhook delivery service. Deferred: on-event, abort, deployed code
loading (code is in the task payload for now), logs/usage/telemetry.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from nango_py.jobs.domain.runner_boundary import (
    NodeRunnerClient,
    RunnerStartParams,
    RunnerTaskResult,
    task_result_to_transition,
)
from nango_py.scheduler.application.orchestrator_service import DequeueRequest, OrchestratorService
from nango_py.scheduler.domain.models import Task

RUNNER_TASK_TYPES = frozenset({"action", "sync", "on-event"})
WEBHOOK_TASK_TYPE = "webhook"

JsonObject = dict[str, Any]


class WebhookDispatch(BaseModel):
    url: str = Field(min_length=1)
    secret: str = Field(min_length=1)
    payload: dict[str, Any]


class JobsProcessorService:
    def __init__(
        self,
        *,
        orchestrator: OrchestratorService,
        runner: NodeRunnerClient,
        webhook_sender: Any | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._runner = runner
        self._webhook_sender = webhook_sender

    async def process_once(
        self,
        *,
        group_key_pattern: str,
        limit: int = 1,
        long_polling: bool = False,
    ) -> list[Task]:
        tasks = await self._orchestrator.dequeue(
            DequeueRequest(
                group_key_pattern=group_key_pattern,
                limit=limit,
                long_polling=long_polling,
            )
        )
        for task in tasks:
            await self.dispatch(task)
        return tasks

    async def dispatch(self, task: Task) -> None:
        payload = task.payload
        if not isinstance(payload, Mapping):
            self._fail(task.id, "task payload must be an object")
            return

        task_type = _task_type(payload)
        if task_type in RUNNER_TASK_TYPES:
            await self._dispatch_runner_task(task, payload)
            return
        if task_type == WEBHOOK_TASK_TYPE:
            await self._dispatch_webhook_task(task, payload)
            return
        self._fail(task.id, f"unsupported task type: {task_type}")

    async def _dispatch_runner_task(
        self, task: Task, payload: Mapping[str, Any]
    ) -> None:

        params = RunnerStartParams(
            taskId=task.id,
            nangoProps={
                "scriptType": _task_type(payload),
                "connection": payload.get("connection"),
                "heartbeatTimeoutSecs": task.heartbeat_timeout_secs,
            },
            code=_string_value(payload.get("code")),
            codeParams={"input": payload.get("input")},
        )
        result = await self._runner.start(params)
        if not result:
            self._fail(task.id, "runner did not start task")

    async def _dispatch_webhook_task(
        self, task: Task, payload: Mapping[str, Any]
    ) -> None:

        if self._webhook_sender is None:
            self._fail(task.id, "webhook sender is not configured")
            return

        dispatch_input = payload.get("input")
        if not isinstance(dispatch_input, dict):
            self._fail(task.id, "webhook task missing input")
            return



        # Delegate to the webhook delivery service
        from nango_py.webhooks.delivery import deliver_webhook

        try:
            dispatch = WebhookDispatch.model_validate(dispatch_input)
        except Exception as exc:
            self._fail(task.id, f"invalid webhook dispatch: {exc}")
            return

        
        result = await deliver_webhook(
            url=dispatch.url,
            payload=dispatch.payload,
            secret=dispatch.secret,
            sender=self._webhook_sender,
        )
        from nango_py.webhooks.delivery import WebhookResponse

        if isinstance(result, WebhookResponse):
            await self._orchestrator.transition(
                task.id,
                "SUCCEEDED",
                {"statusCode": result.status_code},
            )
        else:
            self._fail(task.id, str(result))

    def _fail(self, task_id: str, message: str) -> None:

        self._transition_once(
            task_id,
            "FAILED",
            {"type": "job_dispatch_error", "message": message},
        )

    def _transition_once(
        self, task_id: str, state: str, output: JsonObject
    ) -> None:
        import asyncio

        loop = asyncio.get_event_loop()
        loop.create_task(
            self._orchestrator.transition(task_id, state, output)  # type: ignore[arg-type]
        )

    async def complete_from_runner_result(
        self, result: RunnerTaskResult
    ) -> Task | None:
        transition = task_result_to_transition(result)
        try:
            return await self._orchestrator.transition(
                result.task_id, transition["state"], transition["output"]
            )
        except ValueError as exc:
            if "invalid task transition" in str(exc):
                return None
            raise

    def heartbeat(self, task_id: str) -> None:
        import asyncio

        loop = asyncio.get_event_loop()
        loop.create_task(self._orchestrator.heartbeat(task_id))


def _task_type(payload: Mapping[str, Any]) -> str:
    value = payload.get("type")
    if not isinstance(value, str) or not value:
        return "unknown"
    return value


def _string_value(value: object) -> str:
    if isinstance(value, str):
        return value
    return ""