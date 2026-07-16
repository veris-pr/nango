from typing import Any

from nango.runner import (
    NodeRunnerClient,
    RunnerAbortRequest,
    RunnerHeartbeat,
    RunnerIdleNotification,
    RunnerJobsClient,
    RunnerOperation,
    RunnerOutputError,
    RunnerStartParams,
    RunnerTaskResult,
    abort_response_state,
    task_result_state,
    task_result_to_transition,
)
from nango.scheduler.models import TaskState


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[RunnerOperation, dict[str, Any] | None]] = []

    async def call(self, operation: RunnerOperation, payload: dict[str, Any] | None) -> Any:
        self.calls.append((operation, payload))
        match operation:
            case "runner.health":
                return {"status": "ok"}
            case "runner.start" | "runner.abort" | "runner.notifyWhenIdle":
                return True
            case "jobs.heartbeat" | "jobs.taskResult" | "jobs.idle":
                return None


def test_runner_start_params_serialize_to_node_runner_wire_shape() -> None:
    params = RunnerStartParams(
        taskId="task-1",
        nangoProps={"connectionId": "conn-1", "heartbeatTimeoutSecs": 30},
        code="export default async function run() {}",
        codeParams={"input": {"id": 1}},
    )

    assert params.model_dump(mode="json", by_alias=True, exclude_none=True) == {
        "taskId": "task-1",
        "nangoProps": {"connectionId": "conn-1", "heartbeatTimeoutSecs": 30},
        "code": "export default async function run() {}",
        "codeParams": {"input": {"id": 1}},
    }


async def test_node_runner_client_calls_start_abort_and_idle_through_transport() -> None:
    transport = FakeTransport()
    client = NodeRunnerClient(transport)

    started = await client.start(
        RunnerStartParams(taskId="task-1", nangoProps={}, code="code")
    )
    aborted = await client.abort(RunnerAbortRequest(taskId="task-1"))
    idle_notified = await client.notify_when_idle()

    assert started is True
    assert aborted is True
    assert idle_notified is True
    assert transport.calls == [
        (
            "runner.start",
            {"taskId": "task-1", "nangoProps": {}, "code": "code"},
        ),
        ("runner.abort", {"taskId": "task-1"}),
        ("runner.notifyWhenIdle", None),
    ]


async def test_jobs_client_calls_heartbeat_result_and_idle_through_transport() -> None:
    transport = FakeTransport()
    client = RunnerJobsClient(transport)
    telemetry_bag = {
        "customLogs": 2,
        "proxyCalls": 3,
        "durationMs": 400,
        "memoryGb": 1,
        "futureOpaqueCounter": 9,
    }

    await client.heartbeat(RunnerHeartbeat(taskId="task-1"))
    await client.put_task_result(
        RunnerTaskResult(
            taskId="task-1",
            output={"ok": True},
            telemetryBag=telemetry_bag,
            functionRuntime="runner",
        )
    )
    await client.idle(RunnerIdleNotification(nodeId=7))

    assert transport.calls == [
        ("jobs.heartbeat", {"taskId": "task-1"}),
        (
            "jobs.taskResult",
            {
                "taskId": "task-1",
                "telemetryBag": telemetry_bag,
                "functionRuntime": "runner",
                "output": {"ok": True},
            },
        ),
        ("jobs.idle", {"nodeId": 7}),
    ]


def test_task_result_mapping_success_and_error() -> None:
    success = RunnerTaskResult(
        taskId="task-1",
        output={"created": 1},
        telemetryBag={"durationMs": 1},
        functionRuntime="runner",
    )
    error = RunnerTaskResult(
        taskId="task-2",
        error=RunnerOutputError(type="script_error", payload={"message": "boom"}, status=500),
        telemetryBag={"durationMs": 2},
        functionRuntime="runner",
    )

    assert task_result_state(success) == TaskState.SUCCEEDED
    assert task_result_to_transition(success).model_dump(mode="json", by_alias=True) == {
        "output": {"created": 1},
        "state": "SUCCEEDED",
        "nextExecutionInMs": None,
    }
    assert task_result_state(error) == TaskState.FAILED
    assert task_result_to_transition(error).model_dump(mode="json", by_alias=True) == {
        "output": {"type": "script_error", "payload": {"message": "boom"}, "status": 500},
        "state": "FAILED",
        "nextExecutionInMs": None,
    }


def test_abort_response_mapping() -> None:
    assert abort_response_state(True) == TaskState.CANCELLED
    assert abort_response_state(False) is None
