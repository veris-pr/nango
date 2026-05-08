from __future__ import annotations

import asyncio
import fnmatch
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol


class KeyAlreadyExistsError(Exception):
    """Raised when a key is written without override permission."""


class KVStore(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(
        self,
        key: str,
        value: str,
        *,
        can_override: bool = True,
        ttl_ms: int | None = None,
    ) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...

    async def set_if_value_equals(
        self,
        key: str,
        expected_value: str,
        new_value: str,
        *,
        ttl_ms: int | None = None,
    ) -> bool: ...

    async def delete_if_value_equals(self, key: str, expected_value: str) -> bool: ...

    async def incr(self, key: str, *, ttl_ms: int | None = None, delta: int = 1) -> int: ...

    def scan(self, pattern: str) -> AsyncIterator[str]: ...


@dataclass(frozen=True)
class _Entry:
    value: str
    expires_at: float | None


class InMemoryKVStore:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            entry = self._live_entry(key)
            return None if entry is None else entry.value

    async def set(
        self,
        key: str,
        value: str,
        *,
        can_override: bool = True,
        ttl_ms: int | None = None,
    ) -> None:
        async with self._lock:
            if not can_override and self._live_entry(key) is not None:
                raise KeyAlreadyExistsError("set_key_already_exists")
            self._entries[key] = _Entry(value=value, expires_at=self._expires_at(ttl_ms))

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._entries.pop(key, None)

    async def exists(self, key: str) -> bool:
        async with self._lock:
            return self._live_entry(key) is not None

    async def set_if_value_equals(
        self,
        key: str,
        expected_value: str,
        new_value: str,
        *,
        ttl_ms: int | None = None,
    ) -> bool:
        async with self._lock:
            entry = self._live_entry(key)
            if entry is None or entry.value != expected_value:
                return False
            self._entries[key] = _Entry(value=new_value, expires_at=self._expires_at(ttl_ms))
            return True

    async def delete_if_value_equals(self, key: str, expected_value: str) -> bool:
        async with self._lock:
            entry = self._live_entry(key)
            if entry is None or entry.value != expected_value:
                return False
            self._entries.pop(key, None)
            return True

    async def incr(self, key: str, *, ttl_ms: int | None = None, delta: int = 1) -> int:
        async with self._lock:
            entry = self._live_entry(key)
            next_value = delta if entry is None else int(entry.value) + delta
            self._entries[key] = _Entry(value=str(next_value), expires_at=self._expires_at(ttl_ms))
            return next_value

    async def scan(self, pattern: str) -> AsyncIterator[str]:
        async with self._lock:
            keys = [key for key in list(self._entries) if self._live_entry(key) is not None]
        for key in keys:
            if fnmatch.fnmatchcase(key, pattern):
                yield key

    async def destroy(self) -> None:
        async with self._lock:
            self._entries.clear()

    def _live_entry(self, key: str) -> _Entry | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at is not None and entry.expires_at <= self._clock():
            self._entries.pop(key, None)
            return None
        return entry

    def _expires_at(self, ttl_ms: int | None) -> float | None:
        if ttl_ms is None or ttl_ms <= 0:
            return None
        return self._clock() + ttl_ms / 1000


@dataclass(frozen=True)
class Lock:
    key: str
    token: str


class LockAcquisitionError(Exception):
    """Raised when a lock cannot be acquired before the timeout."""


class AsyncLockManager:
    def __init__(self, store: KVStore) -> None:
        self._store = store

    async def acquire(self, key: str, ttl_ms: int) -> Lock:
        self._validate_ttl(ttl_ms)
        token = secrets.token_urlsafe(24)
        try:
            await self._store.set(key, token, can_override=False, ttl_ms=ttl_ms)
        except KeyAlreadyExistsError as exc:
            raise LockAcquisitionError(f"Failed to acquire lock for key: {key}") from exc
        return Lock(key=key, token=token)

    async def try_acquire(
        self,
        key: str,
        *,
        ttl_ms: int,
        acquisition_timeout_ms: int,
        retry_delay_ms: int = 50,
    ) -> Lock:
        self._validate_ttl(ttl_ms)
        if acquisition_timeout_ms <= 0:
            raise ValueError("acquisition_timeout_ms must be greater than 0")

        deadline = time.monotonic() + acquisition_timeout_ms / 1000
        last_error: LockAcquisitionError | None = None
        while time.monotonic() < deadline:
            try:
                return await self.acquire(key, ttl_ms)
            except LockAcquisitionError as exc:
                last_error = exc
                await asyncio.sleep(retry_delay_ms / 1000)
        raise LockAcquisitionError(
            f"Acquiring lock for key: {key} timed out after {acquisition_timeout_ms}ms"
        ) from last_error

    async def release(self, lock: Lock) -> bool:
        return await self._store.delete_if_value_equals(lock.key, lock.token)

    async def has_lock(self, key: str) -> bool:
        return await self._store.exists(key)

    async def release_all(self, prefix: str) -> None:
        async for key in self._store.scan(f"{prefix}:*"):
            await self._store.delete(key)

    async def with_lock[T](
        self, key: str, ttl_ms: int, acquisition_timeout_ms: int, fn: Callable[[], Awaitable[T]]
    ) -> T:
        lock = await self.try_acquire(
            key,
            ttl_ms=ttl_ms,
            acquisition_timeout_ms=acquisition_timeout_ms,
        )
        try:
            return await fn()
        finally:
            await self.release(lock)

    def _validate_ttl(self, ttl_ms: int) -> None:
        if ttl_ms <= 0:
            raise ValueError("lock's TTL must be greater than 0")


class FeatureFlags:
    def __init__(self, store: KVStore) -> None:
        self._store = store

    async def is_set(
        self, key: str, *, distinct_id: str = "global", fallback: bool = False
    ) -> bool:
        try:
            return await self._store.exists(f"flag:{key}:{distinct_id}")
        except Exception:
            return fallback
