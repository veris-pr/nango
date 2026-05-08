from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from nango.contracts.base import ContractModel


class UserCreatedPayload(ContractModel):
    user_id: int = Field(alias="userId")
    team_id: int = Field(alias="teamId")


class UserCreatedEvent(ContractModel):
    idempotency_key: str = Field(alias="idempotencyKey")
    subject: Literal["user"]
    type: Literal["user.created"]
    payload: UserCreatedPayload
    source: str | None = None
    created_at: datetime = Field(alias="createdAt")


class PubsubEventEnvelope(ContractModel):
    idempotency_key: str = Field(alias="idempotencyKey")
    subject: str
    type: str
    payload: dict[str, Any]
    source: str | None = None
    created_at: datetime = Field(alias="createdAt")
