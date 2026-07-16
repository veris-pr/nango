"""Task and Schedule domain models.

Mirrors ``packages/scheduler/lib/types.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

JsonObject = dict[str, Any]

TaskState = Literal["CREATED", "STARTED", "SUCCEEDED", "FAILED", "EXPIRED", "CANCELLED"]
ScheduleState = Literal["PAUSED", "STARTED", "DELETED"]

TERMINAL_TASK_STATES = frozenset({"SUCCEEDED", "FAILED", "EXPIRED", "CANCELLED"})

VALID_TASK_TRANSITIONS = frozenset({
    ("CREATED", "STARTED"),
    ("STARTED", "SUCCEEDED"),
    ("STARTED", "FAILED"),
    ("STARTED", "CANCELLED"),
    ("STARTED", "EXPIRED"),
    ("CREATED", "EXPIRED"),
    ("CREATED", "CANCELLED"),
})

VALID_SCHEDULE_TRANSITIONS = frozenset({
    ("STARTED", "PAUSED"),
    ("PAUSED", "STARTED"),
    ("STARTED", "DELETED"),
    ("PAUSED", "DELETED"),
})


@dataclass(frozen=True)
class Task:
    id: str
    name: str
    payload: JsonObject
    group_key: str
    group_max_concurrency: int
    retry_max: int
    retry_count: int
    retry_key: str | None
    owner_key: str | None
    starts_after: datetime
    created_to_started_timeout_secs: int
    started_to_completed_timeout_secs: int
    heartbeat_timeout_secs: int
    created_at: datetime
    state: TaskState
    last_state_transition_at: datetime
    last_heartbeat_at: datetime
    output: JsonObject | None
    terminated: bool
    schedule_id: str | None


@dataclass(frozen=True)
class Schedule:
    id: str
    name: str
    state: ScheduleState
    starts_at: datetime
    frequency_ms: int
    payload: JsonObject
    group_key: str
    retry_max: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    last_scheduled_task_id: str | None
    last_scheduled_task_state: TaskState | None
    next_execution_at: datetime


@dataclass(frozen=True)
class ImmediateTaskInput:
    name: str
    payload: JsonObject
    group_key: str
    group_max_concurrency: int
    retry_max: int
    retry_count: int
    retry_key: str | None
    owner_key: str | None
    starts_after: datetime
    created_to_started_timeout_secs: int
    started_to_completed_timeout_secs: int
    heartbeat_timeout_secs: int


@dataclass(frozen=True)
class RecurringScheduleInput:
    name: str
    state: ScheduleState
    starts_at: datetime
    frequency_ms: int
    payload: JsonObject
    group_key: str
    retry_max: int
    created_to_started_timeout_secs: int
    started_to_completed_timeout_secs: int
    heartbeat_timeout_secs: int