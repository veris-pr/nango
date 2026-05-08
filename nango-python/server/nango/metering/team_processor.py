from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from nango.adapters.pubsub import Subscriber
from nango.contracts.pubsub import PubsubEventEnvelope
from nango.metering.events import MeteringTeamUpdatedEvent, team_event_from_envelope

TeamProcessStatus = Literal["ignored_billing_customer_update", "ignored_unknown_event"]
ErrorHandler = Callable[[Exception, PubsubEventEnvelope], Awaitable[None] | None]


@dataclass(frozen=True)
class TeamProcessResult:
    status: TeamProcessStatus
    billing_customer_updated: bool = False


class TeamProcessor:
    def __init__(self, *, transport: Any, on_error: ErrorHandler | None = None) -> None:
        self._subscriber = Subscriber(transport)
        self._on_error = on_error

    def start(self) -> None:
        self._subscriber.subscribe(
            consumer_group="team",
            subject="team",
            callback=self._process_envelope,
        )

    async def process(self, event: MeteringTeamUpdatedEvent) -> TeamProcessResult:
        if event.type == "team.updated":
            return TeamProcessResult(status="ignored_billing_customer_update")
        return TeamProcessResult(status="ignored_unknown_event")

    async def _process_envelope(self, envelope: PubsubEventEnvelope) -> None:
        try:
            await self.process(team_event_from_envelope(envelope))
        except Exception as exc:
            if self._on_error is None:
                raise
            result = self._on_error(exc, envelope)
            if result is not None:
                await result
