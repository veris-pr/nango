from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from nango.contracts.base import ContractModel


class TaskState(StrEnum):
    CREATED = "CREATED"
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ScheduleState(StrEnum):
    PAUSED = "PAUSED"
    STARTED = "STARTED"
    DELETED = "DELETED"


TERMINAL_TASK_STATES = frozenset(
    {
        TaskState.SUCCEEDED,
        TaskState.FAILED,
        TaskState.EXPIRED,
        TaskState.CANCELLED,
    }
)

VALID_TASK_TRANSITIONS = frozenset(
    {
        (TaskState.CREATED, TaskState.STARTED),
        (TaskState.CREATED, TaskState.CANCELLED),
        (TaskState.CREATED, TaskState.EXPIRED),
        (TaskState.STARTED, TaskState.SUCCEEDED),
        (TaskState.STARTED, TaskState.FAILED),
        (TaskState.STARTED, TaskState.CANCELLED),
        (TaskState.STARTED, TaskState.EXPIRED),
    }
)

VALID_SCHEDULE_TRANSITIONS = frozenset(
    {
        (ScheduleState.STARTED, ScheduleState.PAUSED),
        (ScheduleState.STARTED, ScheduleState.DELETED),
        (ScheduleState.PAUSED, ScheduleState.STARTED),
        (ScheduleState.PAUSED, ScheduleState.DELETED),
    }
)


class Task(ContractModel):
    id: str
    name: str
    payload: Any
    group_key: str = Field(alias="groupKey")
    group_max_concurrency: int = Field(alias="groupMaxConcurrency")
    retry_max: int = Field(alias="retryMax")
    retry_count: int = Field(alias="retryCount")
    starts_after: datetime = Field(alias="startsAfter")
    created_to_started_timeout_secs: int = Field(alias="createdToStartedTimeoutSecs")
    started_to_completed_timeout_secs: int = Field(alias="startedToCompletedTimeoutSecs")
    heartbeat_timeout_secs: int = Field(alias="heartbeatTimeoutSecs")
    created_at: datetime = Field(alias="createdAt")
    state: TaskState
    last_state_transition_at: datetime = Field(alias="lastStateTransitionAt")
    last_heartbeat_at: datetime = Field(alias="lastHeartbeatAt")
    output: Any | None
    terminated: bool
    schedule_id: str | None = Field(alias="scheduleId")
    retry_key: str | None = Field(alias="retryKey")
    owner_key: str | None = Field(alias="ownerKey")


class ImmediateTaskInput(ContractModel):
    name: str
    payload: Any
    group_key: str = Field(alias="groupKey")
    group_max_concurrency: int = Field(alias="groupMaxConcurrency")
    retry_max: int = Field(default=0, alias="retryMax")
    retry_count: int = Field(default=0, alias="retryCount")
    created_to_started_timeout_secs: int = Field(alias="createdToStartedTimeoutSecs")
    started_to_completed_timeout_secs: int = Field(alias="startedToCompletedTimeoutSecs")
    heartbeat_timeout_secs: int = Field(alias="heartbeatTimeoutSecs")
    retry_key: str | None = Field(default=None, alias="retryKey")
    owner_key: str | None = Field(default=None, alias="ownerKey")


class Schedule(ContractModel):
    id: str
    name: str
    state: ScheduleState
    starts_at: datetime = Field(alias="startsAt")
    frequency_ms: int = Field(alias="frequencyMs")
    payload: Any
    group_key: str = Field(alias="groupKey")
    retry_max: int = Field(alias="retryMax")
    created_to_started_timeout_secs: int = Field(alias="createdToStartedTimeoutSecs")
    started_to_completed_timeout_secs: int = Field(alias="startedToCompletedTimeoutSecs")
    heartbeat_timeout_secs: int = Field(alias="heartbeatTimeoutSecs")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    deleted_at: datetime | None = Field(alias="deletedAt")
    last_scheduled_task_id: str | None = Field(alias="lastScheduledTaskId")
    last_scheduled_task_state: TaskState | None = Field(alias="lastScheduledTaskState")
    next_execution_at: datetime = Field(alias="nextExecutionAt")


class RecurringScheduleInput(ContractModel):
    name: str
    state: ScheduleState = ScheduleState.STARTED
    starts_at: datetime = Field(alias="startsAt")
    frequency_ms: int = Field(alias="frequencyMs")
    payload: Any
    group_key: str = Field(alias="groupKey")
    retry_max: int = Field(default=0, alias="retryMax")
    created_to_started_timeout_secs: int = Field(alias="createdToStartedTimeoutSecs")
    started_to_completed_timeout_secs: int = Field(alias="startedToCompletedTimeoutSecs")
    heartbeat_timeout_secs: int = Field(alias="heartbeatTimeoutSecs")
