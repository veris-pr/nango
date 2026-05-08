from __future__ import annotations

from typing import Any

from nango.jobs import (
    JobsProcessorService,
    RuntimeInvocation,
    RuntimeRegistry,
    UnsupportedRuntimeAdapter,
)
from nango.orchestrator import OrchestratorService
from nango.runner import RunnerOutputError, RunnerTaskResult
from nango.scheduler import ImmediateTaskInput, SchedulerEngine, TaskState
from nango.utils.result import Err, Ok, Result
from nango.webhooks import WebhookRequest, WebhookResponse


class FakeRuntimeAdapter:
    def __init__(self, result: Result[bool, Exception] | None = None) -> None:
        self.result = result or Ok(True)
        self.invocations: list[RuntimeInvocation] = []

    async def invoke(self, invocation: RuntimeInvocation) -> Result[bool, Exception]:
        self.invocations.append(invocation)
        return self.result

    async def cancel(self, task_id: str) -> Result[bool, Exception]:
        return Ok(True)


async def test_action_task_dispatches_to_runner_runtime() -> None:
    scheduler = SchedulerEngine()
    runner = FakeRuntimeAdapter()
    service = JobsProcessorService(
        orchestrator=OrchestratorService(scheduler),
        runtimes=RuntimeRegistry(runner),
    )
    task = scheduler.immediate(_task_input("action-task", _action_payload()))

    processed = await service.process_once(group_key_pattern="action:*")

    assert [item.id for item in processed] == [task.id]
    assert runner.invocations[0].task_id == task.id
    assert runner.invocations[0].task_type == "action"
    assert runner.invocations[0].code_params == {"input": {"id": 1}}
    assert scheduler.repository.get_task(task.id).state == TaskState.STARTED


async def test_sync_task_dispatches_to_runner_runtime() -> None:
    scheduler = SchedulerEngine()
    runner = FakeRuntimeAdapter()
    service = JobsProcessorService(
        orchestrator=OrchestratorService(scheduler),
        runtimes=RuntimeRegistry(runner),
    )
    task = scheduler.immediate(_task_input("sync-task", _sync_payload()))

    await service.process_once(group_key_pattern="sync:*")

    assert runner.invocations[0].task_id == task.id
    assert runner.invocations[0].task_type == "sync"
    assert runner.invocations[0].nango_props["connection"] == _connection()


async def test_webhook_task_dispatches_to_webhook_service_and_completes() -> None:
    scheduler = SchedulerEngine()
    requests: list[WebhookRequest] = []

    async def sender(request: WebhookRequest) -> WebhookResponse:
        requests.append(request)
        return WebhookResponse(status_code=204)

    service = JobsProcessorService(
        orchestrator=OrchestratorService(scheduler),
        runtimes=RuntimeRegistry(FakeRuntimeAdapter()),
        webhook_sender=sender,
    )
    task = scheduler.immediate(_task_input("webhook-task", _webhook_payload()))

    await service.process_once(group_key_pattern="webhook:*")

    completed = scheduler.repository.get_task(task.id)
    assert completed.state == TaskState.SUCCEEDED
    assert completed.output == {"statusCode": 204}
    assert requests[0].url == "https://example.test/webhook"
    assert requests[0].body == '{"event":"created"}'


async def test_heartbeat_forwards_to_orchestrator_service() -> None:
    scheduler = SchedulerEngine()
    service = JobsProcessorService(
        orchestrator=OrchestratorService(scheduler),
        runtimes=RuntimeRegistry(FakeRuntimeAdapter()),
    )
    task = scheduler.immediate(_task_input("sync-task", _sync_payload()))
    scheduler.dequeue(group_key_pattern="sync:*", limit=1)

    service.heartbeat(task.id)

    assert scheduler.repository.get_task(task.id).state == TaskState.STARTED


def test_runner_result_success_and_failure_complete_tasks() -> None:
    scheduler = SchedulerEngine()
    service = JobsProcessorService(
        orchestrator=OrchestratorService(scheduler),
        runtimes=RuntimeRegistry(FakeRuntimeAdapter()),
    )
    success = scheduler.immediate(_task_input("success", _sync_payload()))
    failure = scheduler.immediate(_task_input("failure", _action_payload()))
    scheduler.dequeue(group_key_pattern="sync:*", limit=1)
    scheduler.dequeue(group_key_pattern="action:*", limit=1)

    service.complete_from_runner_result(
        RunnerTaskResult(
            taskId=success.id,
            output={"ok": True},
            telemetryBag={"durationMs": 1},
            functionRuntime="runner",
        )
    )
    service.complete_from_runner_result(
        RunnerTaskResult(
            taskId=failure.id,
            error=RunnerOutputError(type="script_error", payload={"message": "boom"}, status=500),
            telemetryBag={"durationMs": 2},
            functionRuntime="runner",
        )
    )

    assert scheduler.repository.get_task(success.id).state == TaskState.SUCCEEDED
    assert scheduler.repository.get_task(success.id).output == {"ok": True}
    assert scheduler.repository.get_task(failure.id).state == TaskState.FAILED
    assert scheduler.repository.get_task(failure.id).output == {
        "type": "script_error",
        "payload": {"message": "boom"},
        "status": 500,
    }


async def test_unsupported_runtime_placeholder_fails_task_deterministically() -> None:
    scheduler = SchedulerEngine()
    service = JobsProcessorService(
        orchestrator=OrchestratorService(scheduler),
        runtimes=RuntimeRegistry(FakeRuntimeAdapter()),
    )
    task = scheduler.immediate(_task_input("lambda-task", {**_sync_payload(), "runtime": "lambda"}))

    await service.process_once(group_key_pattern="sync:*")

    failed = scheduler.repository.get_task(task.id)
    assert failed.state == TaskState.FAILED
    assert failed.output == {
        "type": "job_dispatch_error",
        "message": "lambda runtime is not implemented yet",
    }


async def test_unsupported_runtime_adapter_reports_not_implemented() -> None:
    adapter = UnsupportedRuntimeAdapter("fleet")

    result = await adapter.invoke(
        RuntimeInvocation(task_id="task-1", task_type="sync", nango_props={})
    )

    assert isinstance(result, Err)
    assert str(result.error) == "fleet runtime is not implemented yet"


def test_runner_result_telemetry_bag_is_not_interpreted_or_persisted() -> None:
    scheduler = SchedulerEngine()
    service = JobsProcessorService(
        orchestrator=OrchestratorService(scheduler),
        runtimes=RuntimeRegistry(FakeRuntimeAdapter()),
    )
    task = scheduler.immediate(_task_input("telemetry", _sync_payload()))
    scheduler.dequeue(group_key_pattern="sync:*", limit=1)
    telemetry_bag = {"durationMs": 5, "futureOpaqueCounter": {"nested": True}}

    service.complete_from_runner_result(
        RunnerTaskResult(
            taskId=task.id,
            output={"ok": True},
            telemetryBag=telemetry_bag,
            functionRuntime="runner",
        )
    )

    assert scheduler.repository.get_task(task.id).output == {"ok": True}


def _task_input(name: str, payload: dict[str, Any]) -> ImmediateTaskInput:
    return ImmediateTaskInput.model_validate(
        {
            "name": name,
            "payload": payload,
            "groupKey": f"{payload['type']}:test",
            "groupMaxConcurrency": 1,
            "retryMax": 2,
            "retryCount": 0,
            "createdToStartedTimeoutSecs": 30,
            "startedToCompletedTimeoutSecs": 60,
            "heartbeatTimeoutSecs": 10,
        }
    )


def _connection() -> dict[str, Any]:
    return {
        "id": 1,
        "connection_id": "conn-1",
        "provider_config_key": "github",
        "environment_id": 1,
    }


def _sync_payload() -> dict[str, Any]:
    return {
        "type": "sync",
        "syncId": "sync-1",
        "syncName": "issues",
        "syncVariant": "base",
        "debug": False,
        "connection": _connection(),
    }


def _action_payload() -> dict[str, Any]:
    return {
        "type": "action",
        "actionName": "createIssue",
        "activityLogId": "log-1",
        "input": {"id": 1},
        "async": False,
        "connection": _connection(),
    }


def _webhook_payload() -> dict[str, Any]:
    return {
        "type": "webhook",
        "webhookName": "issues",
        "parentSyncName": "issues",
        "activityLogId": "log-1",
        "input": {
            "url": "https://example.test/webhook",
            "secret": "secret",
            "payload": {"event": "created"},
        },
        "connection": _connection(),
    }
