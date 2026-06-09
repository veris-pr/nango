from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from nango.contracts.base import ContractModel, JsonObject

type RecordAction = Literal["ADDED", "UPDATED", "DELETED"]


class RecordMetadata(ContractModel):
    first_seen_at: datetime
    last_modified_at: datetime
    last_action: RecordAction
    deleted_at: datetime | None = None
    cursor: str


class Record(ContractModel):
    id: str
    external_id: str
    connection_id: int
    model: str
    data: JsonObject
    metadata: JsonObject = Field(default_factory=dict)
    record_metadata: RecordMetadata = Field(alias="_nango_metadata")
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    sync_id: str | None = None
    sync_job_id: int | None = None

    @property
    def deleted(self) -> bool:
        return self.deleted_at is not None


class RecordInput(ContractModel):
    external_id: str
    connection_id: int
    model: str
    data: JsonObject
    metadata: JsonObject = Field(default_factory=dict)
    id: str | None = None
    sync_id: str | None = None
    sync_job_id: int | None = None


class ListRecordsResult(ContractModel):
    records: list[Record]
    next_cursor: str | None = None


class RecordCount(ContractModel):
    connection_id: int
    model: str
    count: int
    updated_at: datetime


class RecordCheckpoint(ContractModel):
    connection_id: int
    model: str
    name: str
    cursor: str | None
    updated_at: datetime
