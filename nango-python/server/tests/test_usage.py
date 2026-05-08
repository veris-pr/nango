from __future__ import annotations

from datetime import UTC, datetime

import pytest

import nango.usage as usage
from nango.adapters.kv import InMemoryKVStore
from nango.usage import (
    ClickhouseUsageRepositoryStub,
    InMemoryUsageRepository,
    UsageActionAttributes,
    UsageEvent,
    UsageRecordAttributes,
    UsageTracker,
    usage_event_to_raw,
)


class ManualClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def set(self, current: datetime) -> None:
        self.current = current


def tracker(clock: ManualClock | None = None) -> UsageTracker:
    return UsageTracker(InMemoryUsageRepository(InMemoryKVStore(), clock=clock))


async def test_usage_tracker_increments_counters() -> None:
    subject = tracker()

    counter = await subject.increment(account_id=1, name="records", delta=3)

    assert counter.current == 3


async def test_usage_tracker_checks_caps() -> None:
    subject = tracker()
    await subject.increment(account_id=1, name="records", delta=10)

    status = await subject.check_caps(account_id=1, limits={"records": 10, "connections": 2})

    assert status.is_capped is True
    assert status.counters["records"].is_capped is True
    assert status.counters["connections"].is_capped is False


async def test_usage_tracker_reset_clears_current_window() -> None:
    subject = tracker()
    await subject.increment(account_id=1, name="records", delta=4)

    counter = await subject.reset(account_id=1, name="records")

    assert counter.current == 0


async def test_monthly_usage_uses_current_month_window() -> None:
    clock = ManualClock(datetime(2025, 1, 2, tzinfo=UTC))
    subject = tracker(clock)
    await subject.increment(account_id=1, name="actions", delta=2)
    clock.set(datetime(2025, 2, 1, tzinfo=UTC))

    counter = await subject.get(account_id=1, name="actions")

    assert counter.current == 0
    assert counter.window == "2025-02"


async def test_idempotency_key_prevents_duplicate_increment() -> None:
    subject = tracker()

    first = await subject.increment(
        account_id=1,
        name="proxy",
        delta=5,
        idempotency_key="request-1",
    )
    second = await subject.increment(
        account_id=1,
        name="proxy",
        delta=5,
        idempotency_key="request-1",
    )

    assert first.current == 5
    assert second.current == 5


def test_usage_event_to_raw_matches_clickhouse_contract_names() -> None:
    event = UsageEvent(
        idempotencyKey="event-1",
        type="usage.records",
        accountId=1,
        value=7,
        attributes=UsageRecordAttributes(
            environmentId=2,
            integrationId="github",
            connectionId="conn-1",
            model="Issue",
            syncId="sync-1",
        ),
        createdAt=datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

    raw = usage_event_to_raw(event)

    assert raw.model_dump() == {
        "ts": 1735787045000,
        "idempotency_key": "event-1",
        "type": "usage.records",
        "account_id": 1,
        "value": 7,
        "attributes": {
            "environmentId": 2,
            "integrationId": "github",
            "connectionId": "conn-1",
            "model": "Issue",
            "syncId": "sync-1",
        },
    }


async def test_clickhouse_stub_accepts_action_events_without_client_dependency() -> None:
    repository = ClickhouseUsageRepositoryStub()
    event = UsageEvent(
        idempotencyKey="action-1",
        type="usage.actions",
        accountId=1,
        attributes=UsageActionAttributes(
            environmentId=2,
            integrationId="github",
            connectionId="conn-1",
            actionName="createIssue",
        ),
    )

    await repository.add([event])

    assert repository.raw_events[0].type == "usage.actions"


async def test_clickhouse_stub_querying_is_explicitly_unimplemented() -> None:
    repository = ClickhouseUsageRepositoryStub()

    with pytest.raises(NotImplementedError):
        await repository.get_usage(None)  # type: ignore[arg-type]


def test_usage_module_has_no_billing_surface() -> None:
    assert all("billing" not in exported.lower() for exported in usage.__all__)
    assert not hasattr(UsageTracker, "get_billing_usage")
