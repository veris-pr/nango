from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from nango.contracts.base import ContractModel, JsonObject
from nango.records import ListRecordsResult, RecordCheckpoint

type PersistMode = Literal["save", "update"]


class PersistAuthContext(ContractModel):
    environment_id: int
    token: str
    account_id: int = 0


class PersistRecordInput(ContractModel):
    id: str
    data: JsonObject
    metadata: JsonObject = Field(default_factory=dict)


class PersistRecordsRequest(ContractModel):
    model: str
    records: list[PersistRecordInput]
    provider_config_key: str | None = Field(default=None, alias="providerConfigKey")
    connection_id: str | None = Field(default=None, alias="connectionId")
    activity_log_id: str | None = Field(default=None, alias="activityLogId")
    merging: JsonObject = Field(default_factory=dict)


class DeleteRecordsRequest(ContractModel):
    model: str
    external_ids: list[str] | None = Field(default=None, alias="externalIds")
    records: list[PersistRecordInput] = Field(default_factory=list)
    activity_log_id: str | None = Field(default=None, alias="activityLogId")


class PersistRecordsResponse(ContractModel):
    records: int
    next_merging: JsonObject = Field(default_factory=dict, alias="nextMerging")


class DeleteRecordsResponse(ContractModel):
    deleted: int


class CheckpointRequest(ContractModel):
    model: str
    key: str
    cursor: str | None = None


class CheckpointResponse(ContractModel):
    checkpoint: RecordCheckpoint | None


class PersistLogRequest(ContractModel):
    activity_log_id: str = Field(alias="activityLogId")
    message: str
    level: Literal["debug", "info", "warn", "error"] = "info"
    created_at: datetime = Field(alias="createdAt")
    meta: JsonObject | None = None


class PersistNoopResponse(ContractModel):
    status: Literal["noop"] = "noop"


class ListPersistRecordsResponse(ListRecordsResult):
    pass
