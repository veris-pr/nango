from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from nango.contracts.base import ContractModel

type LogLevel = Literal["debug", "info", "warn", "error"]
type LogSource = Literal["internal", "user"]
type MessageContext = Literal["script", "proxy", "webhook", "auth"]
type MessageType = Literal["log", "http"]
type OperationState = Literal["waiting", "running", "success", "failed", "timeout", "cancelled"]


class OperationDescriptor(ContractModel):
    type: str
    action: str


class LogError(ContractModel):
    name: str
    message: str
    type: str | None = None
    payload: Any | None = None


class HttpRequest(ContractModel):
    url: str
    method: str
    headers: dict[str, str]
    body: Any | None = None


class HttpResponse(ContractModel):
    code: int
    headers: dict[str, str]


class HttpRetry(ContractModel):
    attempt: int
    max: int
    waited: int


class PersistResults(ContractModel):
    model: str
    added: int
    added_keys: list[str] = Field(alias="addedKeys")
    updated: int
    updated_keys: list[str] = Field(alias="updatedKeys")
    unchanged: int
    unchanged_keys: list[str] = Field(alias="unchangedKeys")
    deleted: int
    delete_keys: list[str] = Field(alias="deleteKeys")


class SearchPeriod(ContractModel):
    from_: datetime = Field(alias="from")
    to: datetime


class OperationLogEntry(ContractModel):
    id: str
    source: Literal["internal"] = "internal"
    level: LogLevel = "info"
    type: Literal["operation"] = "operation"
    message: str
    operation: OperationDescriptor
    state: OperationState = "waiting"

    account_id: int = Field(alias="accountId")
    account_name: str = Field(alias="accountName")
    environment_id: int | None = Field(default=None, alias="environmentId")
    environment_name: str | None = Field(default=None, alias="environmentName")
    provider_name: str | None = Field(default=None, alias="providerName")
    integration_id: int | None = Field(default=None, alias="integrationId")
    integration_name: str | None = Field(default=None, alias="integrationName")
    connection_id: int | None = Field(default=None, alias="connectionId")
    connection_name: str | None = Field(default=None, alias="connectionName")
    end_user_id: str | None = Field(default=None, alias="endUserId")
    end_user_name: str | None = Field(default=None, alias="endUserName")
    sync_config_id: int | None = Field(default=None, alias="syncConfigId")
    sync_config_name: str | None = Field(default=None, alias="syncConfigName")
    job_id: str | None = Field(default=None, alias="jobId")
    user_id: int | None = Field(default=None, alias="userId")

    error: LogError | None = None
    request: HttpRequest | None = None
    response: HttpResponse | None = None
    meta: dict[str, Any] | None = None

    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    ended_at: datetime | None = Field(default=None, alias="endedAt")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
    duration_ms: int | None = Field(default=None, alias="durationMs")


class MessageLogEntry(ContractModel):
    id: str
    source: LogSource = "internal"
    level: LogLevel = "info"
    type: MessageType = "log"
    message: str
    context: MessageContext | None = None
    parent_id: str = Field(alias="parentId")
    account_id: int = Field(alias="accountId")

    error: LogError | None = None
    request: HttpRequest | None = None
    response: HttpResponse | None = None
    meta: dict[str, Any] | None = None
    persist_results: PersistResults | None = Field(default=None, alias="persistResults")
    retry: HttpRetry | None = None

    created_at: datetime = Field(alias="createdAt")
    ended_at: datetime | None = Field(default=None, alias="endedAt")
    duration_ms: int | None = Field(default=None, alias="durationMs")


class ListOperationsResult(ContractModel):
    count: int
    items: list[OperationLogEntry]
    cursor: str | None


class ListMessagesResult(ContractModel):
    count: int
    items: list[MessageLogEntry]
    cursor_before: str | None = Field(alias="cursorBefore")
    cursor_after: str | None = Field(alias="cursorAfter")
