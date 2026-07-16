from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from nango.adapters.pubsub import Subscriber
from nango.contracts.pubsub import PubsubEventEnvelope
from nango.metering.events import MeteringUsageEvent, usage_event_from_envelope
from nango.usage.clickhouse import UsageClickhouseRepository
from nango.usage.models import (
    UsageActionAttributes,
    UsageCounterName,
    UsageEvent,
    UsageRecordAttributes,
    UsageUnitAttributes,
)
from nango.usage.tracker import UsageTracker

ErrorHandler = Callable[[Exception, PubsubEventEnvelope], Awaitable[None] | None]

_TRACKED_COUNTERS: dict[str, UsageCounterName] = {
    "usage.actions": "actions",
    "usage.connections": "connections",
    "usage.records": "records",
    "usage.proxy": "proxy",
    "usage.webhook_forward": "webhook_forwards",
}


class UsageProcessor:
    def __init__(
        self,
        *,
        transport: Any,
        usage_tracker: UsageTracker,
        clickhouse: UsageClickhouseRepository,
        on_error: ErrorHandler | None = None,
    ) -> None:
        self._subscriber = Subscriber(transport)
        self._usage_tracker = usage_tracker
        self._clickhouse = clickhouse
        self._on_error = on_error

    def start(self) -> None:
        self._subscriber.subscribe(
            consumer_group="billing",
            subject="usage",
            callback=self._process_envelope,
        )

    async def process(self, event: MeteringUsageEvent) -> None:
        await self._increment_usage_counters(event)
        await self._write_clickhouse_event(event)

    async def _process_envelope(self, envelope: PubsubEventEnvelope) -> None:
        try:
            await self.process(usage_event_from_envelope(envelope))
        except Exception as exc:
            if self._on_error is None:
                raise
            result = self._on_error(exc, envelope)
            if result is not None:
                await result

    async def _increment_usage_counters(self, event: MeteringUsageEvent) -> None:
        counter_name = _TRACKED_COUNTERS.get(event.type)
        if counter_name is not None:
            await self._usage_tracker.increment(
                account_id=_account_id(event),
                name=counter_name,
                delta=_non_negative_int(event.payload.value),
                idempotency_key=event.idempotency_key,
            )
            return

        if event.type == "usage.function_executions":
            account_id = _account_id(event)
            telemetry_bag = _telemetry_bag(event)
            await self._usage_tracker.increment(
                account_id=account_id,
                name="function_executions",
                delta=_non_negative_int(event.payload.value),
                idempotency_key=event.idempotency_key,
            )
            await self._usage_tracker.increment(
                account_id=account_id,
                name="function_compute_gbms",
                delta=_non_negative_int(_compute_gbms(telemetry_bag)),
                idempotency_key=event.idempotency_key,
            )
            await self._usage_tracker.increment(
                account_id=account_id,
                name="function_logs",
                delta=_non_negative_int(telemetry_bag.get("customLogs", 0)),
                idempotency_key=event.idempotency_key,
            )

    async def _write_clickhouse_event(self, event: MeteringUsageEvent) -> None:
        await self._clickhouse.add([_to_usage_event(event)])


def _account_id(event: MeteringUsageEvent) -> int:
    value = event.payload.properties.get("accountId")
    if not isinstance(value, int):
        raise ValueError("usage event properties.accountId must be an integer")
    return value


def _non_negative_int(value: int | float | Any) -> int:
    amount = int(value)
    if amount < 0:
        return 0
    return amount


def _telemetry_bag(event: MeteringUsageEvent) -> dict[str, Any]:
    value = event.payload.properties.get("telemetryBag")
    return value if isinstance(value, dict) else {}


def _compute_gbms(telemetry_bag: dict[str, Any]) -> int | float:
    duration = telemetry_bag.get("durationMs", 0)
    memory = telemetry_bag.get("memoryGb", 0)
    if not isinstance(duration, int | float) or not isinstance(memory, int | float):
        return 0
    return duration * memory


def _to_usage_event(event: MeteringUsageEvent) -> UsageEvent:
    properties = event.payload.properties
    common: dict[str, Any] = {
        "idempotencyKey": event.idempotency_key,
        "type": event.type,
        "accountId": _account_id(event),
        "value": event.payload.value,
        "createdAt": event.created_at,
    }

    attributes: UsageRecordAttributes | UsageActionAttributes | UsageUnitAttributes
    if event.type in {"usage.records", "usage.monthly_active_records"}:
        attributes = UsageRecordAttributes(
            environmentId=_required_int(properties, "environmentId"),
            integrationId=_required_str(properties, "integrationId"),
            connectionId=_required_str(properties, "connectionId"),
            model=_required_str(properties, "model"),
            syncId=_optional_str(properties, "syncId"),
        )
    elif event.type == "usage.actions":
        attributes = UsageActionAttributes(
            environmentId=_required_int(properties, "environmentId"),
            integrationId=_required_str(properties, "integrationId"),
            connectionId=_optional_str(properties, "connectionId") or "",
            actionName=_required_str(properties, "actionName"),
        )
    else:
        attributes = UsageUnitAttributes(
            environmentId=_required_int(properties, "environmentId"),
            integrationId=_required_str(properties, "integrationId"),
            connectionId=_optional_str(properties, "connectionId") or "",
            success=_optional_bool(properties, "success"),
            functionName=_optional_str(properties, "functionName"),
            type=_optional_str(properties, "type"),
            runtime=_optional_str(properties, "runtime"),
            telemetryBag=_optional_dict(properties, "telemetryBag"),
        )

    return UsageEvent(**common, attributes=cast(Any, attributes))


def _required_int(properties: dict[str, Any], name: str) -> int:
    value = properties.get(name)
    if not isinstance(value, int):
        raise ValueError(f"usage event properties.{name} must be an integer")
    return value


def _required_str(properties: dict[str, Any], name: str) -> str:
    value = properties.get(name)
    if not isinstance(value, str) or value == "":
        raise ValueError(f"usage event properties.{name} must be a non-empty string")
    return value


def _optional_str(properties: dict[str, Any], name: str) -> str | None:
    value = properties.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"usage event properties.{name} must be a string")
    return value


def _optional_bool(properties: dict[str, Any], name: str) -> bool | None:
    value = properties.get(name)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"usage event properties.{name} must be a boolean")
    return value


def _optional_dict(properties: dict[str, Any], name: str) -> dict[str, Any] | None:
    value = properties.get(name)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"usage event properties.{name} must be an object")
    return value
