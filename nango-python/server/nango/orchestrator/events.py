from __future__ import annotations

import asyncio
from fnmatch import fnmatchcase


class InMemoryTaskEvents:
    """Task event placeholder for the in-memory scheduler foundation.

    Production should replace this with Postgres LISTEN/NOTIFY using the same
    group-key matching contract so dequeue long-polling can wake across processes.
    """

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._created_group_keys: list[str] = []

    async def notify_task_created(self, group_key: str) -> None:
        async with self._condition:
            self._created_group_keys.append(group_key)
            self._condition.notify_all()

    async def wait_for_task_created(
        self,
        group_key_pattern: str,
        *,
        timeout_seconds: float,
    ) -> None:
        async with self._condition:
            await asyncio.wait_for(
                self._condition.wait_for(
                    lambda: any(
                        fnmatchcase(group_key, group_key_pattern)
                        for group_key in self._created_group_keys
                    )
                ),
                timeout=timeout_seconds,
            )
            self._created_group_keys = [
                group_key
                for group_key in self._created_group_keys
                if not fnmatchcase(group_key, group_key_pattern)
            ]
