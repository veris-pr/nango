from __future__ import annotations

import pytest

from nango.adapters.kv import AsyncLockManager, InMemoryKVStore, KeyAlreadyExistsError, Lock


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def test_in_memory_kv_expires_keys_after_ttl() -> None:
    clock = ManualClock()
    store = InMemoryKVStore(clock=clock)

    await store.set("session", "active", ttl_ms=100)
    clock.advance(0.11)

    assert await store.get("session") is None
    assert not await store.exists("session")


async def test_in_memory_kv_respects_can_override_false() -> None:
    store = InMemoryKVStore()

    await store.set("once", "first", can_override=False)

    with pytest.raises(KeyAlreadyExistsError):
        await store.set("once", "second", can_override=False)


async def test_lock_release_only_removes_matching_holder() -> None:
    store = InMemoryKVStore()
    locking = AsyncLockManager(store)
    lock = await locking.acquire("job", ttl_ms=100)

    await store.set("job", "new-owner", can_override=True, ttl_ms=1000)

    assert not await locking.release(lock)
    assert await store.get("job") == "new-owner"


async def test_expired_lock_can_be_acquired_again() -> None:
    clock = ManualClock()
    store = InMemoryKVStore(clock=clock)
    locking = AsyncLockManager(store)

    await locking.acquire("job", ttl_ms=100)
    clock.advance(0.11)
    second_lock = await locking.acquire("job", ttl_ms=100)

    assert isinstance(second_lock, Lock)
