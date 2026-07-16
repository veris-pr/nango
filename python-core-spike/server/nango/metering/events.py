from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from nango.contracts.base import ContractModel
from nango.contracts.pubsub import PubsubEventEnvelope
from nango.usage.models import UsageEventType

TeamEventType = Literal["team.updated"]


class MeteringUsagePayload(ContractModel):
    value: int | float = 1
    properties: dict[str, Any]


class MeteringUsageEvent(ContractModel):
    idempotency_key: str = Field(alias="idempotencyKey")
    subject: Literal["usage"]
    type: UsageEventType
    payload: MeteringUsagePayload
    source: str | None = None
    created_at: datetime = Field(alias="createdAt")


class MeteringTeamUpdatedPayload(ContractModel):
    id: int
    name: str | None = None


class MeteringTeamUpdatedEvent(ContractModel):
    idempotency_key: str = Field(alias="idempotencyKey")
    subject: Literal["team"]
    type: TeamEventType
    payload: MeteringTeamUpdatedPayload
    source: str | None = None
    created_at: datetime = Field(alias="createdAt")


def usage_event_from_envelope(event: PubsubEventEnvelope) -> MeteringUsageEvent:
    return MeteringUsageEvent.model_validate(event.model_dump(by_alias=True))


def team_event_from_envelope(event: PubsubEventEnvelope) -> MeteringTeamUpdatedEvent:
    return MeteringTeamUpdatedEvent.model_validate(event.model_dump(by_alias=True))
