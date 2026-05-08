from __future__ import annotations

from datetime import UTC, datetime

import nango.metering as metering
from nango.adapters.kv import InMemoryKVStore
from nango.adapters.pubsub import InMemoryPubsubTransport, Publisher
from nango.contracts.pubsub import PubsubEventEnvelope
from nango.metering import (
    ExportUsageCron,
    ExportUsageService,
    MeteringTeamUpdatedEvent,
    MeteringUsageEvent,
    TeamProcessor,
    UsageProcessor,
)
from nango.usage import (
    ClickhouseUsageRepositoryStub,
    InMemoryUsageRepository,
    UsageActionAttributes,
    UsageEvent,
    UsageTracker,
)

CREATED_AT = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)


def usage_envelope(
    *,
    idempotency_key: str = "usage-1",
    event_type: str = "usage.records",
    value: int | float = 3,
    properties: dict[str, object] | None = None,
) -> PubsubEventEnvelope:
    return PubsubEventEnvelope(
        idempotencyKey=idempotency_key,
        subject="usage",
        type=event_type,
        payload={
            "value": value,
            "properties": properties
            or {
                "accountId": 1,
                "environmentId": 2,
                "integrationId": "github",
                "connectionId": "conn-1",
                "model": "Issue",
            },
        },
        createdAt=CREATED_AT,
    )


def team_event() -> MeteringTeamUpdatedEvent:
    return MeteringTeamUpdatedEvent.model_validate(
        {
            "idempotencyKey": "team-1",
            "subject": "team",
            "type": "team.updated",
            "payload": {"id": 1, "name": "Acme"},
            "createdAt": CREATED_AT,
        }
    )


def usage_tracker(store: InMemoryKVStore) -> UsageTracker:
    return UsageTracker(InMemoryUsageRepository(store))


async def test_usage_processor_consumes_pubsub_event_and_updates_usage_tracker() -> None:
    store = InMemoryKVStore()
    transport = InMemoryPubsubTransport()
    await transport.connect()
    clickhouse = ClickhouseUsageRepositoryStub()
    processor = UsageProcessor(
        transport=transport,
        usage_tracker=usage_tracker(store),
        clickhouse=clickhouse,
    )
    processor.start()

    await Publisher(transport).publish(usage_envelope())

    counter = await usage_tracker(store).get(account_id=1, name="records")
    assert counter.current == 3
    assert clickhouse.raw_events[0].type == "usage.records"


async def test_usage_processor_applies_idempotency_key_to_tracker_updates() -> None:
    store = InMemoryKVStore()
    clickhouse = ClickhouseUsageRepositoryStub()
    processor = UsageProcessor(
        transport=InMemoryPubsubTransport(),
        usage_tracker=usage_tracker(store),
        clickhouse=clickhouse,
    )
    event = MeteringUsageEvent.model_validate(usage_envelope().model_dump(by_alias=True))

    await processor.process(event)
    await processor.process(event)

    counter = await usage_tracker(store).get(account_id=1, name="records")
    assert counter.current == 3


async def test_usage_processor_tracks_function_compute_and_logs() -> None:
    store = InMemoryKVStore()
    processor = UsageProcessor(
        transport=InMemoryPubsubTransport(),
        usage_tracker=usage_tracker(store),
        clickhouse=ClickhouseUsageRepositoryStub(),
    )
    event = MeteringUsageEvent.model_validate(
        usage_envelope(
            event_type="usage.function_executions",
            value=2,
            properties={
                "accountId": 1,
                "environmentId": 2,
                "integrationId": "github",
                "connectionId": "conn-1",
                "functionName": "syncIssues",
                "type": "sync",
                "success": True,
                "telemetryBag": {"durationMs": 100, "memoryGb": 2, "customLogs": 4},
            },
        ).model_dump(by_alias=True)
    )

    await processor.process(event)

    executions = await usage_tracker(store).get(account_id=1, name="function_executions")
    compute = await usage_tracker(store).get(account_id=1, name="function_compute_gbms")
    logs = await usage_tracker(store).get(account_id=1, name="function_logs")
    assert (executions.current, compute.current, logs.current) == (2, 200, 4)


async def test_export_usage_service_defaults_to_shadow_mode_without_writes() -> None:
    store = InMemoryKVStore()
    clickhouse = ClickhouseUsageRepositoryStub()
    service = ExportUsageService(store=store, clickhouse=clickhouse)
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

    result = await service.export(export_id="run-1", events=[event])

    assert result.shadow_mode is True
    assert result.exported_event_count == 0
    assert clickhouse.raw_events == []


async def test_export_usage_service_skips_duplicate_export_id() -> None:
    store = InMemoryKVStore()
    service = ExportUsageService(
        store=store,
        clickhouse=ClickhouseUsageRepositoryStub(),
        shadow_mode=False,
    )

    first = await service.export(export_id="run-1", events=[])
    second = await service.export(export_id="run-1", events=[])

    assert (first.status, second.status) == ("completed", "skipped")


async def test_export_usage_cron_placeholder_runs_empty_shadow_export() -> None:
    cron = ExportUsageCron(
        ExportUsageService(store=InMemoryKVStore(), clickhouse=ClickhouseUsageRepositoryStub())
    )

    result = await cron.run_once(export_id="cron-1")

    assert result.status == "completed"
    assert result.exported_event_count == 0


async def test_team_processor_explicitly_excludes_billing_customer_updates() -> None:
    processor = TeamProcessor(transport=InMemoryPubsubTransport())

    result = await processor.process(team_event())

    assert result.status == "ignored_billing_customer_update"
    assert result.billing_customer_updated is False


def test_metering_module_has_no_billing_surface() -> None:
    assert all("billing" not in exported.lower() for exported in metering.__all__)
