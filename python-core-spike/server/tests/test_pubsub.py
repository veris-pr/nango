from __future__ import annotations

from datetime import UTC, datetime

from nango.adapters.pubsub import InMemoryPubsubTransport, Publisher, Subscriber
from nango.contracts import PubsubEventEnvelope


def event(subject: str = "user") -> PubsubEventEnvelope:
    return PubsubEventEnvelope.model_validate(
        {
            "idempotencyKey": "event-1",
            "subject": subject,
            "type": f"{subject}.created",
            "payload": {"id": 1},
            "createdAt": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
        }
    )


async def test_in_memory_pubsub_delivers_matching_subject_events() -> None:
    transport = InMemoryPubsubTransport()
    await transport.connect()
    received: list[PubsubEventEnvelope] = []

    Subscriber(transport).subscribe(
        consumer_group="workers",
        subject="user",
        callback=received.append,
    )

    await Publisher(transport).publish(event("team"))
    await Publisher(transport).publish(event("user"))

    assert [item.subject for item in received] == ["user"]


async def test_in_memory_pubsub_awaits_async_subscribers() -> None:
    transport = InMemoryPubsubTransport()
    await transport.connect()
    received: list[str] = []

    async def collect(item: PubsubEventEnvelope) -> None:
        received.append(item.idempotency_key)

    Subscriber(transport).subscribe(consumer_group="workers", subject="user", callback=collect)

    await Publisher(transport).publish(event("user"))

    assert received == ["event-1"]
