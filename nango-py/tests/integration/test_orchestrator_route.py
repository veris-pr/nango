"""E2e tests for orchestrator routes: immediate, recurring, dequeue, heartbeat, transition."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.server.app import create_app

BASE_PUBLIC_URL = "https://public.test"

_IMMEDIATE_BODY = {
    "name": "test-task",
    "ownerKey": "",
    "group": {"key": "test-group", "maxConcurrency": 1},
    "retry": {"count": 0, "max": 0},
    "timeoutSettingsInSecs": {
        "createdToStarted": 30,
        "startedToCompleted": 300,
        "heartbeat": 30,
    },
    "args": {"type": "action", "actionName": "my-action"},
}


@pytest.fixture
async def app_and_client(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> tuple[Any, AsyncClient]:
    app = create_app(
        session_factory=db_session_factory,
        encryption_key="",
        base_public_url=BASE_PUBLIC_URL,
        webhook_receive_url="https://webhook.test",
    )
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return app, client


async def test_create_immediate_returns_task_id(
    app_and_client: tuple[Any, AsyncClient],
) -> None:
    _, client = app_and_client
    response = await client.post("/orchestrator/v1/immediate", json=_IMMEDIATE_BODY)
    assert response.status_code == 200
    data = response.json()
    assert "taskId" in data
    assert "retryKey" in data
    assert len(data["taskId"]) > 0


async def test_duplicate_task_name_rejected(
    app_and_client: tuple[Any, AsyncClient],
) -> None:
    _, client = app_and_client
    await client.post("/orchestrator/v1/immediate", json=_IMMEDIATE_BODY)
    response = await client.post("/orchestrator/v1/immediate", json=_IMMEDIATE_BODY)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_task_name"


async def test_dequeue_returns_started_tasks(
    app_and_client: tuple[Any, AsyncClient],
) -> None:
    _, client = app_and_client
    await client.post("/orchestrator/v1/immediate", json=_IMMEDIATE_BODY)
    response = await client.post(
        "/orchestrator/v1/dequeue",
        json={"groupKeyPattern": "test-group", "limit": 10, "longPolling": False},
    )
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 1
    assert tasks[0]["state"] == "STARTED"
    assert tasks[0]["name"] == "test-task"


async def test_dequeue_respects_group_concurrency(
    app_and_client: tuple[Any, AsyncClient],
) -> None:
    _, client = app_and_client
    # Create 2 tasks in the same group with maxConcurrency=1
    for i in range(2):
        body = {**_IMMEDIATE_BODY, "name": f"task-{i}"}
        await client.post("/orchestrator/v1/immediate", json=body)
    # Dequeue should only start 1 (one already STARTED counts against concurrency)
    response = await client.post(
        "/orchestrator/v1/dequeue",
        json={"groupKeyPattern": "test-group", "limit": 10, "longPolling": False},
    )
    tasks = response.json()
    assert len(tasks) == 1
    # Second dequeue should return 0 (group is at capacity)
    response2 = await client.post(
        "/orchestrator/v1/dequeue",
        json={"groupKeyPattern": "test-group", "limit": 10, "longPolling": False},
    )
    assert len(response2.json()) == 0


async def test_heartbeat_updates_started_task(
    app_and_client: tuple[Any, AsyncClient],
) -> None:
    _, client = app_and_client
    create_resp = await client.post("/orchestrator/v1/immediate", json=_IMMEDIATE_BODY)
    task_id = create_resp.json()["taskId"]
    await client.post(
        "/orchestrator/v1/dequeue",
        json={"groupKeyPattern": "test-group", "limit": 10, "longPolling": False},
    )
    response = await client.post(f"/orchestrator/v1/tasks/{task_id}/heartbeat")
    assert response.status_code == 200
    assert response.json()["taskId"] == task_id


async def test_complete_transitions_to_succeeded(
    app_and_client: tuple[Any, AsyncClient],
) -> None:
    _, client = app_and_client
    create_resp = await client.post("/orchestrator/v1/immediate", json=_IMMEDIATE_BODY)
    task_id = create_resp.json()["taskId"]
    await client.post(
        "/orchestrator/v1/dequeue",
        json={"groupKeyPattern": "test-group", "limit": 10, "longPolling": False},
    )
    response = await client.put(
        f"/orchestrator/v1/tasks/{task_id}",
        json={"state": "SUCCEEDED", "output": {"result": "ok"}},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "SUCCEEDED"
    assert response.json()["terminated"] is True


async def test_fail_transitions_to_failed(
    app_and_client: tuple[Any, AsyncClient],
) -> None:
    _, client = app_and_client
    create_resp = await client.post("/orchestrator/v1/immediate", json=_IMMEDIATE_BODY)
    task_id = create_resp.json()["taskId"]
    await client.post(
        "/orchestrator/v1/dequeue",
        json={"groupKeyPattern": "test-group", "limit": 10, "longPolling": False},
    )
    response = await client.put(
        f"/orchestrator/v1/tasks/{task_id}",
        json={"state": "FAILED", "output": {"error": "something went wrong"}},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "FAILED"


async def test_create_recurring_returns_schedule_id(
    app_and_client: tuple[Any, AsyncClient],
) -> None:
    _, client = app_and_client
    now = datetime.now(UTC).isoformat()
    body = {
        "name": "test-schedule",
        "state": "STARTED",
        "startsAt": now,
        "frequencyMs": 3600000,
        "group": {"key": "sched-group", "maxConcurrency": 1},
        "retry": {"max": 0},
        "timeoutSettingsInSecs": {
            "createdToStarted": 30,
            "startedToCompleted": 300,
            "heartbeat": 30,
        },
        "args": {"type": "sync", "syncName": "my-sync"},
    }
    response = await client.post("/orchestrator/v1/recurring", json=body)
    assert response.status_code == 200
    assert "scheduleId" in response.json()


async def test_dequeue_empty_without_tasks(
    app_and_client: tuple[Any, AsyncClient],
) -> None:
    _, client = app_and_client
    response = await client.post(
        "/orchestrator/v1/dequeue",
        json={"groupKeyPattern": "nonexistent", "limit": 10, "longPolling": False},
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_invalid_transition_rejected(
    app_and_client: tuple[Any, AsyncClient],
) -> None:
    _, client = app_and_client
    create_resp = await client.post("/orchestrator/v1/immediate", json=_IMMEDIATE_BODY)
    task_id = create_resp.json()["taskId"]
    # Try SUCCEEDED on a CREATED task (invalid — must go through STARTED first)
    response = await client.put(
        f"/orchestrator/v1/tasks/{task_id}",
        json={"state": "SUCCEEDED", "output": {}},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "put_task_failed"