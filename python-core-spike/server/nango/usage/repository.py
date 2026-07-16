from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from nango.adapters.kv import KeyAlreadyExistsError, KVStore
from nango.usage.models import UsageCounter, UsageCounterName

COUNTER_DEFINITIONS: Mapping[UsageCounterName, str] = {
    "actions": "monthly",
    "connections": "never",
    "function_compute_gbms": "monthly",
    "function_executions": "monthly",
    "function_logs": "monthly",
    "proxy": "monthly",
    "records": "never",
    "webhook_forwards": "monthly",
}


class InMemoryUsageRepository:
    def __init__(
        self,
        store: KVStore,
        *,
        clock: Callable[[], datetime] | None = None,
        prefix: str = "usage:v1",
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._prefix = prefix

    async def get(self, *, account_id: int, name: UsageCounterName) -> UsageCounter:
        key = self._counter_key(account_id, name)
        raw_value = await self._store.get(key)
        return UsageCounter(
            accountId=account_id,
            name=name,
            current=0 if raw_value is None else int(raw_value),
            window=self._window_for(name),
        )

    async def get_all(self, *, account_id: int) -> dict[UsageCounterName, UsageCounter]:
        counters: dict[UsageCounterName, UsageCounter] = {}
        for name in COUNTER_DEFINITIONS:
            counters[name] = await self.get(account_id=account_id, name=name)
        return counters

    async def increment(
        self,
        *,
        account_id: int,
        name: UsageCounterName,
        delta: int = 1,
        idempotency_key: str | None = None,
    ) -> UsageCounter:
        if delta < 0:
            raise ValueError("delta must be greater than or equal to 0")

        key = self._counter_key(account_id, name)
        if idempotency_key is not None:
            try:
                await self._store.set(
                    self._idempotency_key(account_id, name, idempotency_key),
                    "1",
                    can_override=False,
                )
            except KeyAlreadyExistsError:
                return await self.get(account_id=account_id, name=name)

        current = await self._store.incr(key, delta=delta)
        return UsageCounter(
            accountId=account_id,
            name=name,
            current=current,
            window=self._window_for(name),
        )

    async def reset(self, *, account_id: int, name: UsageCounterName) -> UsageCounter:
        await self._store.delete(self._counter_key(account_id, name))
        return await self.get(account_id=account_id, name=name)

    def _counter_key(self, account_id: int, name: UsageCounterName) -> str:
        window = self._window_for(name)
        if window is None:
            return f"{self._prefix}:counter:{account_id}:{name}"
        return f"{self._prefix}:counter:{account_id}:{name}:{window}"

    def _idempotency_key(self, account_id: int, name: UsageCounterName, value: str) -> str:
        window = self._window_for(name) or "all"
        return f"{self._prefix}:idempotency:{account_id}:{name}:{window}:{value}"

    def _window_for(self, name: UsageCounterName) -> str | None:
        if COUNTER_DEFINITIONS[name] == "monthly":
            return self._clock().strftime("%Y-%m")
        return None
