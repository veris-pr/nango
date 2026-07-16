from __future__ import annotations

from collections.abc import Mapping

from nango.usage.models import UsageCap, UsageCapStatus, UsageCounter, UsageCounterName
from nango.usage.repository import InMemoryUsageRepository


class UsageTracker:
    def __init__(self, repository: InMemoryUsageRepository) -> None:
        self._repository = repository

    async def get(self, *, account_id: int, name: UsageCounterName) -> UsageCounter:
        return await self._repository.get(account_id=account_id, name=name)

    async def increment(
        self,
        *,
        account_id: int,
        name: UsageCounterName,
        delta: int = 1,
        idempotency_key: str | None = None,
    ) -> UsageCounter:
        return await self._repository.increment(
            account_id=account_id,
            name=name,
            delta=delta,
            idempotency_key=idempotency_key,
        )

    async def reset(self, *, account_id: int, name: UsageCounterName) -> UsageCounter:
        return await self._repository.reset(account_id=account_id, name=name)

    async def check_caps(
        self,
        *,
        account_id: int,
        limits: Mapping[UsageCounterName, int | float | None],
    ) -> UsageCapStatus:
        caps: dict[UsageCounterName, UsageCap] = {}
        capped_names: list[str] = []

        for name, limit in limits.items():
            if limit is None:
                continue
            counter = await self.get(account_id=account_id, name=name)
            is_capped = counter.current >= limit
            caps[name] = UsageCap(limit=limit, current=counter.current, isCapped=is_capped)
            if is_capped:
                capped_names.append(name)

        message = None
        if capped_names:
            joined_names = ", ".join(sorted(capped_names))
            message = f"Usage cap reached for: {joined_names}."

        return UsageCapStatus(
            accountId=account_id,
            isCapped=bool(capped_names),
            counters=caps,
            message=message,
        )
