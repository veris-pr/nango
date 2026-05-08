from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from nango.orchestrator import OrchestratorService
from nango.orchestrator.models import DequeueRequest, TaskTransitionRequest
from nango.runner import RunnerTaskResult, task_result_to_transition
from nango.scheduler import Task
from nango.utils.result import Err
from nango.webhooks import deliver_webhook
from nango.webhooks.delivery import WebhookSender

from .runtime import RuntimeInvocation, RuntimeName, RuntimeRegistry

RUNNER_TASK_TYPES = frozenset({"action", "sync", "on-event"})
WEBHOOK_TASK_TYPE = "webhook"


class WebhookDispatch(BaseModel):
    url: str = Field(min_length=1)
    secret: str = Field(min_length=1)
    payload: dict[str, Any]


class JobsProcessorService:
    def __init__(
        self,
        *,
        orchestrator: OrchestratorService,
        runtimes: RuntimeRegistry,
        webhook_sender: WebhookSender | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._runtimes = runtimes
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
                groupKeyPattern=group_key_pattern,
                limit=limit,
                longPolling=long_polling,
            )
        )
        for task in tasks:
            await self.dispatch(task)
        return tasks

    async def dispatch(self, task: Task) -> None:
        payload = _task_payload(task)
        task_type = _task_type(payload)

        if task_type in RUNNER_TASK_TYPES:
            await self._dispatch_runner_task(task, payload)
            return

        if task_type == WEBHOOK_TASK_TYPE:
            await self._dispatch_webhook_task(task, payload)
            return

        await self._fail_task(task.id, f"unsupported task type: {task_type}")

    def heartbeat(self, task_id: str) -> None:
        self._orchestrator.heartbeat(task_id)

    def complete_from_runner_result(self, result: RunnerTaskResult) -> Task | None:
        return self._transition_once(result.task_id, task_result_to_transition(result))

    async def _dispatch_runner_task(self, task: Task, payload: Mapping[str, Any]) -> None:
        runtime = _runtime_name(payload)
        adapter = self._runtimes.adapter_for(runtime)
        invocation = _runtime_invocation(task, payload)
        result = await adapter.invoke(invocation)

        if isinstance(result, Err):
            await self._fail_task(task.id, str(result.error))
            return
        if result.value is False:
            await self._fail_task(task.id, "runner did not start task")

    async def _dispatch_webhook_task(self, task: Task, payload: Mapping[str, Any]) -> None:
        if self._webhook_sender is None:
            await self._fail_task(task.id, "webhook sender is not configured")
            return

        dispatch = WebhookDispatch.model_validate(payload.get("input"))
        result = await deliver_webhook(
            url=dispatch.url,
            payload=dispatch.payload,
            secret=dispatch.secret,
            sender=self._webhook_sender,
        )
        if not isinstance(result, Err):
            self._transition_once(
                task.id,
                TaskTransitionRequest(
                    state="SUCCEEDED",
                    output={"statusCode": result.value.status_code},
                ),
            )
            return

        await self._fail_task(task.id, str(result.error))

    async def _fail_task(self, task_id: str, message: str) -> None:
        self._transition_once(
            task_id,
            TaskTransitionRequest(
                state="FAILED",
                output={"type": "job_dispatch_error", "message": message},
            ),
        )

    def _transition_once(
        self,
        task_id: str,
        request: TaskTransitionRequest,
    ) -> Task | None:
        try:
            return self._orchestrator.transition_task(task_id, request)
        except ValueError as exc:
            if "invalid task transition" in str(exc):
                return None
            raise


def _task_payload(task: Task) -> Mapping[str, Any]:
    if not isinstance(task.payload, Mapping):
        raise ValueError("task payload must be an object")
    return task.payload


def _task_type(payload: Mapping[str, Any]) -> str:
    value = payload.get("type")
    if not isinstance(value, str) or not value:
        return "unknown"
    return value


def _runtime_name(payload: Mapping[str, Any]) -> RuntimeName:
    runtime = payload.get("runtime", "runner")
    if runtime == "runner":
        return "runner"
    if runtime == "lambda":
        return "lambda"
    if runtime == "fleet":
        return "fleet"
    if runtime == "sqs":
        return "sqs"
    return "runner"


def _runtime_invocation(task: Task, payload: Mapping[str, Any]) -> RuntimeInvocation:
    return RuntimeInvocation(
        task_id=task.id,
        task_type=_task_type(payload),
        nango_props={
            "scriptType": _task_type(payload),
            "connection": payload.get("connection"),
            "heartbeatTimeoutSecs": task.heartbeat_timeout_secs,
        },
        code=_string_value(payload.get("code")),
        code_params={"input": payload.get("input")},
    )


def _string_value(value: object) -> str:
    if isinstance(value, str):
        return value
    return ""
