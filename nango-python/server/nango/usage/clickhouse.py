from __future__ import annotations

from typing import Protocol

from nango.usage.models import ClickhouseRawUsageEvent, UsageEvent, UsageQuery

RAW_EVENTS_TABLE = """
raw_events(ts DateTime64(3), idempotency_key String, type LowCardinality(String),
account_id Int64, value Float64, attributes JSON)
""".strip()

DAILY_TABLES = (
    "daily_actions",
    "daily_connections",
    "daily_function_executions",
    "daily_mar",
    "daily_proxy",
    "daily_records",
    "daily_webhook_forwards",
)


class UsageClickhouseRepository(Protocol):
    async def add_raw(self, events: list[ClickhouseRawUsageEvent]) -> None: ...

    async def add(self, events: list[UsageEvent]) -> None: ...


class ClickhouseUsageRepositoryStub:
    """No-client ClickHouse boundary for the future usage adapter.

    The raw DTO matches packages/usage/lib/clickhouse/migrations raw_events.
    Daily table names mirror the TypeScript materialized-view targets. This stub
    intentionally stores rows in memory and does not query ClickHouse.
    """

    def __init__(self) -> None:
        self.raw_events: list[ClickhouseRawUsageEvent] = []

    async def add_raw(self, events: list[ClickhouseRawUsageEvent]) -> None:
        self.raw_events.extend(events)

    async def add(self, events: list[UsageEvent]) -> None:
        await self.add_raw([usage_event_to_raw(event) for event in events])

    async def get_usage(self, _query: UsageQuery) -> None:
        raise NotImplementedError("ClickHouse usage querying is not implemented in Python yet")


def usage_event_to_raw(event: UsageEvent) -> ClickhouseRawUsageEvent:
    return ClickhouseRawUsageEvent(
        ts=int(event.created_at.timestamp() * 1000),
        idempotency_key=event.idempotency_key,
        type=event.type,
        account_id=event.account_id,
        value=event.value,
        attributes=event.attributes.model_dump(by_alias=True, exclude_none=True),
    )
