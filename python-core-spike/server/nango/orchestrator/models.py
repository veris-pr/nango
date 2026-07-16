from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from nango.contracts.base import ContractModel
from nango.scheduler.models import TaskState


class ConnectionPayload(ContractModel):
    id: int = Field(gt=0)
    connection_id: str = Field(min_length=1)
    provider_config_key: str = Field(min_length=1)
    environment_id: int = Field(gt=0)


class SyncTaskPayload(ContractModel):
    type: Literal["sync"]
    sync_id: str = Field(alias="syncId", min_length=1)
    sync_name: str = Field(alias="syncName", min_length=1)
    sync_variant: str = Field(default="base", alias="syncVariant", min_length=1)
    debug: bool
    connection: ConnectionPayload


class ActionTaskPayload(ContractModel):
    type: Literal["action"]
    action_name: str = Field(alias="actionName", min_length=1)
    activity_log_id: str = Field(alias="activityLogId")
    input: Any
    async_: bool = Field(default=False, alias="async")
    connection: ConnectionPayload


class WebhookTaskPayload(ContractModel):
    type: Literal["webhook"]
    webhook_name: str = Field(alias="webhookName", min_length=1)
    parent_sync_name: str = Field(alias="parentSyncName", min_length=1)
    activity_log_id: str = Field(alias="activityLogId")
    input: Any
    connection: ConnectionPayload


class OnEventTaskPayload(ContractModel):
    type: Literal["on-event"]
    on_event_name: str = Field(alias="onEventName", min_length=1)
    version: str = Field(min_length=1)
    file_location: str = Field(alias="fileLocation", min_length=1)
    sdk_version: str | None = Field(alias="sdkVersion")
    activity_log_id: str = Field(alias="activityLogId")
    connection: ConnectionPayload


class AbortedTaskPayload(ContractModel):
    id: str
    state: TaskState


class AbortTaskPayload(ContractModel):
    type: Literal["abort"]
    aborted_task: AbortedTaskPayload = Field(alias="abortedTask")
    reason: str = Field(min_length=1)
    connection: ConnectionPayload


class SyncAbortTaskPayload(AbortTaskPayload):
    sync_id: str = Field(alias="syncId", min_length=1)
    sync_name: str = Field(alias="syncName", min_length=1)
    sync_variant: str = Field(default="base", alias="syncVariant", min_length=1)
    debug: bool


type ImmediateTaskPayload = (
    SyncTaskPayload
    | ActionTaskPayload
    | WebhookTaskPayload
    | OnEventTaskPayload
    | SyncAbortTaskPayload
    | AbortTaskPayload
)


class TaskGroupRequest(ContractModel):
    key: str = Field(min_length=1)
    max_concurrency: int = Field(alias="maxConcurrency", ge=0)


class ImmediateRetryRequest(ContractModel):
    count: int = Field(ge=0)
    max: int = Field(ge=0)


class RecurringRetryRequest(ContractModel):
    max: int = Field(ge=0)


class TimeoutSettingsRequest(ContractModel):
    created_to_started: int = Field(alias="createdToStarted", gt=0)
    started_to_completed: int = Field(alias="startedToCompleted", gt=0)
    heartbeat: int = Field(gt=0)


class ImmediateTaskCreateRequest(ContractModel):
    name: str = Field(min_length=1)
    owner_key: str = Field(default="", alias="ownerKey")
    group: TaskGroupRequest
    retry: ImmediateRetryRequest
    timeout_settings_in_secs: TimeoutSettingsRequest = Field(alias="timeoutSettingsInSecs")
    args: ImmediateTaskPayload

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_group_key(cls, data: Any) -> Any:
        if isinstance(data, dict) and "groupKey" in data and "group" not in data:
            return {**data, "group": {"key": data["groupKey"], "maxConcurrency": 0}}
        return data


class RecurringScheduleCreateRequest(ContractModel):
    name: str = Field(min_length=1)
    state: Literal["STARTED", "PAUSED"]
    starts_at: datetime = Field(alias="startsAt")
    frequency_ms: int = Field(alias="frequencyMs", gt=0)
    group: TaskGroupRequest
    retry: RecurringRetryRequest
    timeout_settings_in_secs: TimeoutSettingsRequest = Field(alias="timeoutSettingsInSecs")
    args: SyncTaskPayload

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_group_key(cls, data: Any) -> Any:
        if isinstance(data, dict) and "groupKey" in data and "group" not in data:
            return {**data, "group": {"key": data["groupKey"], "maxConcurrency": 0}}
        return data


class DequeueRequest(ContractModel):
    group_key_pattern: str = Field(alias="groupKeyPattern", min_length=1)
    limit: int = Field(gt=0)
    long_polling: bool = Field(alias="longPolling")


class TaskTransitionRequest(ContractModel):
    output: Any = None
    state: Literal["SUCCEEDED", "FAILED", "CANCELLED"]
    next_execution_in_ms: int | None = Field(default=None, alias="nextExecutionInMs", ge=0)


class ImmediateTaskCreateResponse(ContractModel):
    task_id: str = Field(alias="taskId")
    retry_key: str = Field(alias="retryKey")


class RecurringScheduleCreateResponse(ContractModel):
    schedule_id: str = Field(alias="scheduleId")


class HeartbeatResponse(ContractModel):
    task_id: str = Field(alias="taskId")
    last_heartbeat_at: datetime = Field(alias="lastHeartbeatAt")
