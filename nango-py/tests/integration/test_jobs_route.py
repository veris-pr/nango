"""E2e tests for jobs callback routes + processor dispatch with mock runner."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.jobs.domain.runner_boundary import (
    RunnerStartParams,
)
from nango_py.server.app import create_app

BASE_PUBLIC_URL = "https://public.test"

_IMMEDIATE_BODY = {
    "name": "test-action",
    "ownerKey": "",
    "group": {"key": "jobs-group", "maxConcurrency": 1},
    "retry": {"count": 0, "max": 0},
    "timeoutSettingsInSecs": {
        "createdToStarted": 30,
        "startedToCompleted": 300,
        "heartbeat": 30,
    },
    "args": {
        "type": "action",
        "actionName": "my-action",
        "code": "module.exports = async () => 'ok'",
    },
}


class _MockRunnerTransport:
    def __init__(self) -> None:
        self.started: list[RunnerStartParams] = []

    async def call(self, operation: str, payload: dict[str, Any] | None) -> Any:
        if operation == "runner.start":
            params = RunnerStartParams.model_validate(payload)
            self.started.append(params)
            return True
        if operation == "runner.health":
            return {"status": "ok"}
        if operation == "runner.abort":
            return True
        return None


@pytest.fixture
async def app_and_client(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> tuple[Any, AsyncClient, _MockRunnerTransport, async_sessionmaker[AsyncSession]]:
    from nango_py.jobs.application.processor import JobsProcessorService
    from nango_py.jobs.domain.runner_boundary import NodeRunnerClient
    from nango_py.scheduler.application.orchestrator_service import OrchestratorService
    from nango_py.scheduler.infrastructure.postgres_scheduler_repository import (
        PostgresSchedulerRepository,
    )

    transport = _MockRunnerTransport()
    runner_client = NodeRunnerClient(transport)
    scheduler_repo = PostgresSchedulerRepository(db_session_factory)
    orchestrator = OrchestratorService(scheduler_repo)
    jobs_processor = JobsProcessorService(
        orchestrator=orchestrator, runner=runner_client
    )

    app = create_app(
        session_factory=db_session_factory,
        encryption_key="",
        base_public_url=BASE_PUBLIC_URL,
        webhook_receive_url="https://webhook.test",
    )
    # Override the placeholder runner transport
    app.state.runner_transport = transport
    app.state.jobs_processor = jobs_processor

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return app, client, transport, db_session_factory


async def test_processor_dispatches_action_to_runner(
    app_and_client: tuple[Any, AsyncClient, _MockRunnerTransport, Any],
) -> None:
    app, client, transport, sf = app_and_client

    # Create a task via orchestrator
    create_resp = await client.post("/orchestrator/v1/immediate", json=_IMMEDIATE_BODY)
    task_id = create_resp.json()["taskId"]

    # Dequeue (STARTED state)
    await client.post(
        "/orchestrator/v1/dequeue",
        json={"groupKeyPattern": "jobs-group", "limit": 10, "longPolling": False},
    )

    # Process via the jobs processor
    processor = app.state.jobs_processor

    # Dispatch the task (already dequeued, simulate with a manual task fetch)

    # Re-fetch the started task and dispatch it
    from sqlalchemy import text

    async with sf() as session:
        row = (
            await session.execute(
                text("SELECT * FROM tasks WHERE id = :id LIMIT 1"), {"id": task_id}
            )
        ).mappings().first()

    assert row is not None
    from typing import cast


    task = _row_to_task(cast(dict[str, Any], row))
    await processor.dispatch(task)

    assert len(transport.started) == 1
    assert transport.started[0].task_id == task_id
    assert transport.started[0].code == "module.exports = async () => 'ok'"


async def test_runner_result_callback_completes_task(
    app_and_client: tuple[Any, AsyncClient, _MockRunnerTransport, Any],
) -> None:
    app, client, _, _ = app_and_client

    create_resp = await client.post("/orchestrator/v1/immediate", json=_IMMEDIATE_BODY)
    task_id = create_resp.json()["taskId"]
    await client.post(
        "/orchestrator/v1/dequeue",
        json={"groupKeyPattern": "jobs-group", "limit": 10, "longPolling": False},
    )

    # Simulate runner result callback
    response = await client.put(
        f"/jobs/tasks/{task_id}",
        json={
            "taskId": task_id,
            "telemetryBag": {},
            "functionRuntime": "runner",
            "output": {"result": "success"},
        },
    )

    assert response.status_code == 200
    assert response.json()["state"] == "SUCCEEDED"
    assert response.json()["terminated"] is True


async def test_runner_error_callback_fails_task(
    app_and_client: tuple[Any, AsyncClient, _MockRunnerTransport, Any],
) -> None:
    app, client, _, _ = app_and_client

    create_resp = await client.post("/orchestrator/v1/immediate", json=_IMMEDIATE_BODY)
    task_id = create_resp.json()["taskId"]
    await client.post(
        "/orchestrator/v1/dequeue",
        json={"groupKeyPattern": "jobs-group", "limit": 10, "longPolling": False},
    )

    response = await client.put(
        f"/jobs/tasks/{task_id}",
        json={
            "taskId": task_id,
            "telemetryBag": {},
            "functionRuntime": "runner",
            "error": {"type": "script_error", "payload": {"message": "boom"}, "status": 500},
        },
    )

    assert response.status_code == 200
    assert response.json()["state"] == "FAILED"


async def test_heartbeat_callback(
    app_and_client: tuple[Any, AsyncClient, _MockRunnerTransport, Any],
) -> None:
    app, client, _, _ = app_and_client

    create_resp = await client.post("/orchestrator/v1/immediate", json=_IMMEDIATE_BODY)
    task_id = create_resp.json()["taskId"]
    await client.post(
        "/orchestrator/v1/dequeue",
        json={"groupKeyPattern": "jobs-group", "limit": 10, "longPolling": False},
    )

    response = await client.post(f"/jobs/tasks/{task_id}/heartbeat")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def _row_to_task(row: dict[str, Any]) -> Any:
    from nango_py.scheduler.domain.models import Task

    return Task(
        id=str(row["id"]),
        name=row["name"],
        payload=row.get("payload") or {},
        group_key=row["group_key"],
        group_max_concurrency=row["group_max_concurrency"],
        retry_max=row["retry_max"],
        retry_count=row["retry_count"],
        retry_key=str(row["retry_key"]) if row.get("retry_key") else None,
        owner_key=row.get("owner_key"),
        starts_after=row["starts_after"],
        created_to_started_timeout_secs=row["created_to_started_timeout_secs"],
        started_to_completed_timeout_secs=row["started_to_completed_timeout_secs"],
        heartbeat_timeout_secs=row["heartbeat_timeout_secs"],
        created_at=row["created_at"],
        state=row["state"],
        last_state_transition_at=row["last_state_transition_at"],
        last_heartbeat_at=row["last_heartbeat_at"],
        output=row.get("output"),
        terminated=row["terminated"],
        schedule_id=str(row["schedule_id"]) if row.get("schedule_id") else None,
    )