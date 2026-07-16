from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nango.adapters.kv import KeyAlreadyExistsError, KVStore
from nango.usage.clickhouse import UsageClickhouseRepository
from nango.usage.models import UsageEvent

ExportStatus = Literal["completed", "skipped"]


@dataclass(frozen=True)
class ExportUsageResult:
    status: ExportStatus
    export_id: str
    shadow_mode: bool
    exported_event_count: int


class ExportUsageService:
    def __init__(
        self,
        *,
        store: KVStore,
        clickhouse: UsageClickhouseRepository,
        shadow_mode: bool = True,
        key_prefix: str = "metering:export:v1",
    ) -> None:
        self._store = store
        self._clickhouse = clickhouse
        self._shadow_mode = shadow_mode
        self._key_prefix = key_prefix

    async def export(self, *, export_id: str, events: list[UsageEvent]) -> ExportUsageResult:
        try:
            await self._store.set(self._idempotency_key(export_id), "1", can_override=False)
        except KeyAlreadyExistsError:
            return ExportUsageResult(
                status="skipped",
                export_id=export_id,
                shadow_mode=self._shadow_mode,
                exported_event_count=0,
            )

        if self._shadow_mode:
            return ExportUsageResult(
                status="completed",
                export_id=export_id,
                shadow_mode=True,
                exported_event_count=0,
            )

        await self._clickhouse.add(events)
        return ExportUsageResult(
            status="completed",
            export_id=export_id,
            shadow_mode=False,
            exported_event_count=len(events),
        )

    def _idempotency_key(self, export_id: str) -> str:
        return f"{self._key_prefix}:{export_id}"


class ExportUsageCron:
    def __init__(self, service: ExportUsageService) -> None:
        self._service = service

    async def run_once(self, *, export_id: str) -> ExportUsageResult:
        return await self._service.export(export_id=export_id, events=[])
