from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import ASGITransport, AsyncClient

from nango.orchestrator import OrchestratorService
from nango.orchestrator.models import (
    DequeueRequest,
    ImmediateTaskCreateRequest,
    TaskTransitionRequest,
)
from nango.scheduler import SchedulerEngine, TaskState
from nango.server.app import create_app
from nango.server.settings import Settings

BASE_TIME = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)


class ManualClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


async def test_service_create_dequeue_heartbeat_and_complete() -> None:
    clock = ManualClock(BASE_TIME)
    service = OrchestratorService(SchedulerEngine(clock=clock))
    created = await service.create_immediate(_immediate_request("service-task"))

    dequeued = await service.dequeue(
        DequeueRequest(groupKeyPattern="sync:*", limit=1, longPolling=False)
    )
    clock.advance(3)
    heartbeat = service.heartbeat(created.task_id)
    completed = service.transition_task(
        created.task_id,
        TaskTransitionRequest(state="SUCCEEDED", output={"ok": True}),
    )

    assert [task.id for task in dequeued] == [created.task_id]
    assert heartbeat.last_heartbeat_at == BASE_TIME + timedelta(seconds=3)
    assert completed.state == TaskState.SUCCEEDED
    assert completed.output == {"ok": True}


async def test_routes_create_dequeue_heartbeat_and_complete() -> None:
    app = create_app(Settings(service_name="test-core"))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/orchestrator/v1/immediate",
            json=_immediate_body("route-task"),
        )
        task_id = created.json()["taskId"]

        dequeued = await client.post(
            "/orchestrator/v1/dequeue",
            json={"groupKeyPattern": "sync:*", "limit": 1, "longPolling": False},
        )
        heartbeat = await client.post(f"/orchestrator/v1/tasks/{task_id}/heartbeat")
        completed = await client.put(
            f"/orchestrator/v1/tasks/{task_id}",
            json={"state": "SUCCEEDED", "output": {"ok": True}},
        )
        health = await client.get("/health")

    assert created.status_code == 200
    assert dequeued.status_code == 200
    assert dequeued.json()[0]["id"] == task_id
    assert heartbeat.status_code == 200
    assert heartbeat.json()["taskId"] == task_id
    assert completed.status_code == 200
    assert completed.json()["state"] == "SUCCEEDED"
    assert health.status_code == 200


async def test_route_creates_recurring_schedule() -> None:
    app = create_app(Settings(service_name="test-core"))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/orchestrator/v1/recurring",
            json={
                "name": "hourly-sync",
                "state": "STARTED",
                "startsAt": BASE_TIME.isoformat(),
                "frequencyMs": 60_000,
                "group": {"key": "sync:github", "maxConcurrency": 1},
                "retry": {"max": 2},
                "timeoutSettingsInSecs": _timeouts(),
                "args": _sync_args(),
            },
        )

    assert response.status_code == 200
    assert response.json()["scheduleId"]


async def test_route_rejects_invalid_task_payload() -> None:
    app = create_app(Settings(service_name="test-core"))
    transport = ASGITransport(app=app)
    body = _immediate_body("invalid-payload")
    body["args"] = {"type": "sync", "syncId": "", "debug": True}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/orchestrator/v1/immediate", json=body)

    assert response.status_code == 422


def _immediate_request(name: str) -> ImmediateTaskCreateRequest:
    return ImmediateTaskCreateRequest.model_validate(_immediate_body(name))


def _immediate_body(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "ownerKey": "owner",
        "group": {"key": "sync:github", "maxConcurrency": 1},
        "retry": {"count": 0, "max": 2},
        "timeoutSettingsInSecs": _timeouts(),
        "args": _sync_args(),
    }


def _timeouts() -> dict[str, int]:
    return {
        "createdToStarted": 30,
        "startedToCompleted": 60,
        "heartbeat": 10,
    }


def _sync_args() -> dict[str, Any]:
    return {
        "type": "sync",
        "syncId": "sync-1",
        "syncName": "github-issues",
        "syncVariant": "base",
        "debug": False,
        "connection": {
            "id": 1,
            "connection_id": "conn-1",
            "provider_config_key": "github",
            "environment_id": 1,
        },
    }
