from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from nango.contracts.base import ContractModel, JsonObject

UsageCounterName = Literal[
    "actions",
    "connections",
    "function_compute_gbms",
    "function_executions",
    "function_logs",
    "proxy",
    "records",
    "webhook_forwards",
]
UsageEventType = Literal[
    "usage.actions",
    "usage.connections",
    "usage.function_executions",
    "usage.monthly_active_records",
    "usage.proxy",
    "usage.records",
    "usage.webhook_forward",
]
UsageReset = Literal["monthly", "never"]
UsageGranularity = Literal["day", "none"]
UsageDimension = Literal[
    "none",
    "connection_id",
    "environment_id",
    "function_name",
    "function_type",
    "integration_id",
    "model",
    "success",
]

class UsageCounterDefinition(ContractModel):
    name: UsageCounterName
    reset: UsageReset


class UsageCounter(ContractModel):
    account_id: int = Field(alias="accountId")
    name: UsageCounterName
    current: int | float
    window: str | None = None


class UsageCap(ContractModel):
    limit: int | float | None
    current: int | float
    is_capped: bool = Field(alias="isCapped")


class UsageCapStatus(ContractModel):
    account_id: int = Field(alias="accountId")
    is_capped: bool = Field(alias="isCapped")
    counters: dict[UsageCounterName, UsageCap]
    message: str | None = None


class UsageRecordAttributes(ContractModel):
    environment_id: int = Field(alias="environmentId")
    integration_id: str = Field(alias="integrationId")
    connection_id: str = Field(alias="connectionId")
    model: str
    sync_id: str | None = Field(default=None, alias="syncId")


class UsageActionAttributes(ContractModel):
    environment_id: int = Field(alias="environmentId")
    integration_id: str = Field(alias="integrationId")
    connection_id: str = Field(alias="connectionId")
    action_name: str = Field(alias="actionName")


class UsageUnitAttributes(ContractModel):
    environment_id: int = Field(alias="environmentId")
    integration_id: str = Field(alias="integrationId")
    connection_id: str = Field(alias="connectionId")
    success: bool | None = None
    function_name: str | None = Field(default=None, alias="functionName")
    function_type: str | None = Field(default=None, alias="type")
    runtime: str | None = None
    telemetry_bag: JsonObject | None = Field(default=None, alias="telemetryBag")


class UsageEvent(ContractModel):
    idempotency_key: str = Field(alias="idempotencyKey")
    type: UsageEventType
    account_id: int = Field(alias="accountId")
    value: int | float = 1
    attributes: UsageRecordAttributes | UsageActionAttributes | UsageUnitAttributes
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), alias="createdAt")


class ClickhouseRawUsageEvent(ContractModel):
    ts: int
    idempotency_key: str
    type: UsageEventType
    account_id: int
    value: int | float
    attributes: JsonObject


class UsageTimeframe(ContractModel):
    start: datetime
    end: datetime


class UsageQueryMetric(ContractModel):
    dimension: UsageDimension = "none"


class UsageQuery(ContractModel):
    account_id: int = Field(alias="accountId")
    metrics: dict[UsageCounterName, UsageQueryMetric]
    granularity: UsageGranularity
    timeframe: UsageTimeframe
