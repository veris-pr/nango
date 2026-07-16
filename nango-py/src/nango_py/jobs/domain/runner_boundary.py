"""Runner boundary: wire DTOs and transport protocol.

Mirrors the TypeScript runner tRPC interface:
- ``runner.start`` → ``{taskId, nangoProps, code, codeParams?}`` → ``bool``
- ``runner.abort`` → ``{taskId}`` → ``bool``
- ``runner.health`` → ``{status: "ok"}``
- ``runner.notifyWhenIdle`` → ``bool``

The Python jobs layer calls the Node runner over HTTP; the runner sends results
back via jobs callbacks (``PUT /tasks/:taskId`` + ``POST /tasks/:taskId/heartbeat``).
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

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
    async def call(
        self, operation: RunnerOperation, payload: dict[str, Any] | None
    ) -> Any: ...


class RunnerStartParams(BaseModel):
    task_id: str = Field(alias="taskId", min_length=1)
    nango_props: dict[str, Any] = Field(alias="nangoProps")
    code: str
    code_params: dict[str, Any] | None = Field(default=None, alias="codeParams")


class RunnerAbortRequest(BaseModel):
    task_id: str = Field(alias="taskId", min_length=1)


class RunnerTaskResult(BaseModel):
    task_id: str = Field(alias="taskId", min_length=1)
    telemetry_bag: dict[str, Any] = Field(alias="telemetryBag")
    function_runtime: FunctionRuntime = Field(alias="functionRuntime")
    nango_props: dict[str, Any] | None = Field(default=None, alias="nangoProps")
    output: Any = None
    error: dict[str, Any] | None = None
    checkpoints: dict[str, Any] | None = None


class NodeRunnerClient:
    def __init__(self, transport: RunnerTransport) -> None:
        self._transport = transport

    async def health(self) -> bool:
        response = await self._transport.call("runner.health", None)
        return response is not None

    async def start(self, params: RunnerStartParams) -> bool:
        response = await self._transport.call(
            "runner.start", params.model_dump(by_alias=True, exclude_none=True)
        )
        return bool(response)

    async def abort(self, request: RunnerAbortRequest) -> bool:
        response = await self._transport.call(
            "runner.abort", request.model_dump(by_alias=True)
        )
        return bool(response)

    async def notify_when_idle(self) -> bool:
        response = await self._transport.call("runner.notifyWhenIdle", None)
        return bool(response)


def task_result_state(result: RunnerTaskResult) -> TaskTransitionState:
    if result.error is not None:
        return "FAILED"
    return "SUCCEEDED"


def task_result_to_transition(
    result: RunnerTaskResult,
) -> dict[str, Any]:
    state = task_result_state(result)
    output = result.error if result.error is not None else result.output
    return {"state": state, "output": output}