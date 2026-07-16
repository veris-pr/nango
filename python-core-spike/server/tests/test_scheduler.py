from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from nango.scheduler import (
    ImmediateTaskInput,
    RecurringScheduleInput,
    SchedulerEngine,
    ScheduleState,
    Task,
    TaskState,
)

BASE_TIME = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)


class ManualClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock(BASE_TIME)


@pytest.fixture
def scheduler(clock: ManualClock) -> SchedulerEngine:
    return SchedulerEngine(clock=clock)


def immediate_input(
    name: str,
    *,
    group_key: str = "sync:github",
    group_max_concurrency: int = 1,
) -> ImmediateTaskInput:
    return ImmediateTaskInput.model_validate(
        {
            "name": name,
            "payload": {"name": name},
            "groupKey": group_key,
            "groupMaxConcurrency": group_max_concurrency,
            "retryMax": 2,
            "retryCount": 0,
            "createdToStartedTimeoutSecs": 30,
            "startedToCompletedTimeoutSecs": 60,
            "heartbeatTimeoutSecs": 10,
            "ownerKey": "owner",
        }
    )


def schedule_input(name: str) -> RecurringScheduleInput:
    return RecurringScheduleInput.model_validate(
        {
            "name": name,
            "startsAt": BASE_TIME,
            "frequencyMs": 60_000,
            "payload": {"schedule": name},
            "groupKey": "sync:github",
            "retryMax": 1,
            "createdToStartedTimeoutSecs": 30,
            "startedToCompletedTimeoutSecs": 60,
            "heartbeatTimeoutSecs": 10,
        }
    )


def started_task_ids(scheduler: SchedulerEngine, limit: int = 10) -> list[str]:
    return [task.id for task in scheduler.dequeue(group_key_pattern="sync:*", limit=limit)]


def test_create_and_dequeue_orders_ready_tasks(
    scheduler: SchedulerEngine,
    clock: ManualClock,
) -> None:
    first = scheduler.immediate(immediate_input("first", group_max_concurrency=0))
    clock.advance(1)
    second = scheduler.immediate(immediate_input("second", group_max_concurrency=0))

    assert started_task_ids(scheduler) == [first.id, second.id]


def test_dequeue_matches_group_pattern_and_group_limit(
    scheduler: SchedulerEngine,
    clock: ManualClock,
) -> None:
    github = scheduler.immediate(
        immediate_input("github", group_key="sync:github", group_max_concurrency=1)
    )
    clock.advance(1)
    scheduler.immediate(
        immediate_input("github-later", group_key="sync:github", group_max_concurrency=1)
    )
    clock.advance(1)
    scheduler.immediate(
        immediate_input("slack", group_key="sync:slack", group_max_concurrency=1)
    )

    dequeued = scheduler.dequeue(group_key_pattern="sync:g*", limit=10)

    assert [task.id for task in dequeued] == [github.id]
    assert all(task.group_key == "sync:github" for task in dequeued)


def test_heartbeat_updates_started_task(scheduler: SchedulerEngine, clock: ManualClock) -> None:
    task = scheduler.immediate(immediate_input("heartbeat"))
    started = scheduler.dequeue(group_key_pattern="sync:*", limit=1)[0]
    clock.advance(5)

    heartbeat = scheduler.heartbeat(task.id)

    assert started.last_heartbeat_at == BASE_TIME
    assert heartbeat.last_heartbeat_at == BASE_TIME + timedelta(seconds=5)


def test_complete_fail_and_cancel_state_transitions(
    scheduler: SchedulerEngine,
) -> None:
    succeeded, failed, cancelled = _started_tasks(scheduler, "succeeded", "failed", "cancelled")

    assert scheduler.complete(succeeded.id, {"ok": True}).state == TaskState.SUCCEEDED
    assert scheduler.fail(failed.id, {"message": "boom"}).state == TaskState.FAILED
    assert scheduler.cancel(cancelled.id, "not needed").state == TaskState.CANCELLED
    assert scheduler.repository.get_task(cancelled.id).output == {"reason": "not needed"}


def test_invalid_terminal_transition_is_rejected(scheduler: SchedulerEngine) -> None:
    task = scheduler.immediate(immediate_input("invalid"))

    with pytest.raises(ValueError, match="invalid task transition"):
        scheduler.complete(task.id)


def test_recurring_schedule_representation(scheduler: SchedulerEngine) -> None:
    schedule = scheduler.recurring(schedule_input("hourly-sync"))

    assert schedule.name == "hourly-sync"
    assert schedule.state == ScheduleState.STARTED
    assert schedule.starts_at == BASE_TIME
    assert schedule.frequency_ms == 60_000
    assert schedule.next_execution_at == BASE_TIME
    assert schedule.last_scheduled_task_id is None
    assert schedule.model_dump(mode="json", by_alias=True)["frequencyMs"] == 60_000


def test_schedule_state_transition(scheduler: SchedulerEngine) -> None:
    schedule = scheduler.recurring(schedule_input("pausable-sync"))

    paused = scheduler.set_schedule_state(schedule.id, ScheduleState.PAUSED)
    deleted = scheduler.set_schedule_state(schedule.id, ScheduleState.DELETED)

    assert paused.state == ScheduleState.PAUSED
    assert deleted.state == ScheduleState.DELETED
    assert deleted.deleted_at == BASE_TIME


def test_schedule_task_updates_schedule_after_completion(
    scheduler: SchedulerEngine,
    clock: ManualClock,
) -> None:
    schedule = scheduler.recurring(schedule_input("scheduled"))
    task = scheduler.immediate_from_schedule("scheduled")
    scheduler.dequeue(group_key_pattern="sync:*", limit=1)
    clock.advance(90)

    scheduler.complete(task.id, {"ok": True})

    updated = scheduler.repository.get_schedule(schedule.id)
    assert updated.last_scheduled_task_id == task.id
    assert updated.last_scheduled_task_state == TaskState.SUCCEEDED
    assert updated.next_execution_at == BASE_TIME + timedelta(minutes=2)


def test_no_duplicate_dequeue_while_task_is_leased(scheduler: SchedulerEngine) -> None:
    task = scheduler.immediate(immediate_input("leased", group_max_concurrency=0))

    first = started_task_ids(scheduler)
    second = started_task_ids(scheduler)

    assert first == [task.id]
    assert second == []


def test_backpressure_and_expiry_placeholders(scheduler: SchedulerEngine) -> None:
    scheduler.immediate(immediate_input("one", group_max_concurrency=1))
    scheduler.immediate(immediate_input("two", group_max_concurrency=1))

    assert scheduler.groups_with_backpressure(limit=10) == [("sync:github", 2)]
    assert scheduler.expire_timed_out_tasks() == []


def _started_tasks(scheduler: SchedulerEngine, *names: str) -> Iterator[Task]:
    for name in names:
        scheduler.immediate(immediate_input(name, group_max_concurrency=0))
    yield from scheduler.dequeue(group_key_pattern="sync:*", limit=len(names))
