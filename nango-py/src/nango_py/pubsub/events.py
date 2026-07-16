"""Pubsub event envelope and types.

Mirrors ``packages/types/lib/pubsub/events.ts``:
``{idempotencyKey, subject, type, payload, source?, createdAt}``
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

JsonObject = dict[str, Any]


class PubsubEvent(BaseModel):
    model_config = {"extra": "allow"}

    idempotency_key: str = Field(alias="idempotencyKey")
    subject: str
    type: str
    payload: JsonObject
    source: str | None = None
    created_at: datetime = Field(alias="createdAt")


class InMemoryPubsubTransport:
    """In-memory transport for tests and single-process dev."""

    def __init__(self) -> None:
        self._published: list[PubsubEvent] = []

    async def publish(self, event: PubsubEvent) -> None:
        self._published.append(event)

    @property
    def published(self) -> list[PubsubEvent]:
        return list(self._published)


class PubsubPublisher:
    def __init__(self, transport: InMemoryPubsubTransport) -> None:
        self._transport = transport

    async def publish(
        self,
        *,
        subject: str,
        type: str,
        payload: JsonObject,
        idempotency_key: str | None = None,
        source: str | None = None,
    ) -> None:
        import uuid

        event = PubsubEvent(
            idempotencyKey=idempotency_key or str(uuid.uuid4()),
            subject=subject,
            type=type,
            payload=payload,
            source=source,
            createdAt=datetime.now(UTC),
        )
        await self._transport.publish(event)


from datetime import UTC  # noqa: E402