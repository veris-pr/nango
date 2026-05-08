from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from nango.runner import NodeRunnerClient, RunnerAbortRequest, RunnerStartParams
from nango.utils.result import Err, Ok, Result

RuntimeName = Literal["runner", "lambda", "fleet", "sqs"]


class UnsupportedRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeInvocation:
    task_id: str
    task_type: str
    nango_props: dict[str, Any]
    code: str = ""
    code_params: dict[str, Any] = field(default_factory=dict)


class RuntimeAdapter(Protocol):
    async def invoke(self, invocation: RuntimeInvocation) -> Result[bool, Exception]:
        pass

    async def cancel(self, task_id: str) -> Result[bool, Exception]:
        pass


class NodeRunnerRuntimeAdapter:
    def __init__(self, client: NodeRunnerClient) -> None:
        self._client = client

    async def invoke(self, invocation: RuntimeInvocation) -> Result[bool, Exception]:
        try:
            started = await self._client.start(
                RunnerStartParams(
                    taskId=invocation.task_id,
                    nangoProps=invocation.nango_props,
                    code=invocation.code,
                    codeParams=invocation.code_params or None,
                )
            )
            return Ok(started)
        except Exception as exc:
            return Err(exc)

    async def cancel(self, task_id: str) -> Result[bool, Exception]:
        try:
            cancelled = await self._client.abort(RunnerAbortRequest(taskId=task_id))
            return Ok(cancelled)
        except Exception as exc:
            return Err(exc)


class UnsupportedRuntimeAdapter:
    def __init__(self, runtime: RuntimeName) -> None:
        self._runtime = runtime

    async def invoke(self, invocation: RuntimeInvocation) -> Result[bool, Exception]:
        return Err(UnsupportedRuntimeError(f"{self._runtime} runtime is not implemented yet"))

    async def cancel(self, task_id: str) -> Result[bool, Exception]:
        return Err(UnsupportedRuntimeError(f"{self._runtime} runtime is not implemented yet"))


class RuntimeRegistry:
    def __init__(self, runner: RuntimeAdapter) -> None:
        self._adapters: dict[RuntimeName, RuntimeAdapter] = {
            "runner": runner,
            "lambda": UnsupportedRuntimeAdapter("lambda"),
            "fleet": UnsupportedRuntimeAdapter("fleet"),
            "sqs": UnsupportedRuntimeAdapter("sqs"),
        }

    def adapter_for(self, runtime: RuntimeName = "runner") -> RuntimeAdapter:
        return self._adapters[runtime]
