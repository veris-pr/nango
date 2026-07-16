"""
Stable Python boundary for the existing TypeScript runner.

The Python scheduler/jobs core owns task state, retries, heartbeats, and result
persistence. The Node runner owns JavaScript execution for deployed Nango
functions. The runner-sdk is the library those functions use while executing
inside the Node runner; it is not the service boundary itself.

Node remains the execution runtime while Python orchestration is introduced so
existing integrations, runner-sdk behavior, and TypeScript contracts keep
working. This module mirrors only the internal wire DTOs the Python jobs layer
needs to start/abort runner tasks and consume runner callbacks. Compatibility
fields such as telemetryBag are intentionally opaque and passed through without
adding billing or telemetry behavior.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import Field

from nango.contracts.base import ContractModel
from nango.orchestrator.models import TaskTransitionRequest
from nango.scheduler.models import TaskState

RunnerOperation = Literal[
    "runner.health",
    "runner.start",
    "runner.abort",
    "runner.notifyWhenIdle",
    "jobs.heartbeat",
    "jobs.taskResult",
    "jobs.idle",
]
FunctionRuntime = Literal["runner", "lambda"]
TaskTransitionState = Literal["SUCCEEDED", "FAILED", "CANCELLED"]


class RunnerTransport(Protocol):
    """Minimal injectable transport for HTTP, tRPC, or in-process tests."""

    async def call(self, operation: RunnerOperation, payload: dict[str, Any] | None) -> Any:
        """Call a runner-boundary operation with JSON-like alias field names."""


class RunnerHealthResponse(ContractModel):
    status: Literal["ok"]


class RunnerStartParams(ContractModel):
    task_id: str = Field(alias="taskId", min_length=1)
    nango_props: dict[str, Any] = Field(alias="nangoProps")
    code: str
    code_params: dict[str, Any] | None = Field(default=None, alias="codeParams")


class RunnerAbortRequest(ContractModel):
    task_id: str = Field(alias="taskId", min_length=1)


class RunnerHeartbeat(ContractModel):
    task_id: str = Field(alias="taskId", min_length=1)


class RunnerOutputError(ContractModel):
    type: str = Field(min_length=1)
    payload: dict[str, Any] | list[Any]
    status: int
    additional_properties: dict[str, Any] | None = Field(
        default=None,
        alias="additional_properties",
    )


class CheckpointRange(ContractModel):
    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)


class RunnerTaskResult(ContractModel):
    task_id: str = Field(alias="taskId", min_length=1)
    telemetry_bag: dict[str, Any] = Field(alias="telemetryBag")
    function_runtime: FunctionRuntime = Field(alias="functionRuntime")
    nango_props: dict[str, Any] | None = Field(default=None, alias="nangoProps")
    output: Any = None
    error: RunnerOutputError | None = None
    checkpoints: CheckpointRange | None = None


class RunnerIdleNotification(ContractModel):
    node_id: int = Field(alias="nodeId", ge=0)


class NodeRunnerClient:
    def __init__(self, transport: RunnerTransport) -> None:
        self._transport = transport

    async def health(self) -> RunnerHealthResponse:
        response = await self._transport.call("runner.health", None)
        return RunnerHealthResponse.model_validate(response)

    async def start(self, params: RunnerStartParams) -> bool:
        response = await self._transport.call("runner.start", _to_wire(params))
        return bool(response)

    async def abort(self, request: RunnerAbortRequest) -> bool:
        response = await self._transport.call("runner.abort", _to_wire(request))
        return bool(response)

    async def notify_when_idle(self) -> bool:
        response = await self._transport.call("runner.notifyWhenIdle", None)
        return bool(response)


class RunnerJobsClient:
    def __init__(self, transport: RunnerTransport) -> None:
        self._transport = transport

    async def heartbeat(self, heartbeat: RunnerHeartbeat) -> None:
        await self._transport.call("jobs.heartbeat", _to_wire(heartbeat))

    async def put_task_result(self, result: RunnerTaskResult) -> None:
        await self._transport.call("jobs.taskResult", _to_wire(result))

    async def idle(self, notification: RunnerIdleNotification) -> None:
        await self._transport.call("jobs.idle", _to_wire(notification))


def task_result_state(result: RunnerTaskResult) -> TaskState:
    if result.error is not None:
        return TaskState.FAILED
    return TaskState.SUCCEEDED


def task_result_to_transition(result: RunnerTaskResult) -> TaskTransitionRequest:
    state = _transition_state(task_result_state(result))
    output = (
        result.error.model_dump(mode="json", by_alias=True, exclude_none=True)
        if result.error
        else result.output
    )
    return TaskTransitionRequest(output=output, state=state)


def abort_response_state(aborted: bool) -> TaskState | None:
    if not aborted:
        return None
    return TaskState.CANCELLED


def _transition_state(state: TaskState) -> TaskTransitionState:
    match state:
        case TaskState.SUCCEEDED:
            return "SUCCEEDED"
        case TaskState.FAILED:
            return "FAILED"
        case TaskState.CANCELLED:
            return "CANCELLED"
        case _:
            raise ValueError(f"Task state {state} cannot be used as a runner transition")


def _to_wire(model: ContractModel) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)
