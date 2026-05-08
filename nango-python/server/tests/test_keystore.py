from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nango.keystore import (
    InMemoryPrivateKeyRepository,
    PrivateKeyEntityType,
    PrivateKeyNotFoundError,
    hash_private_key_value,
)


class ManualClock:
    def __init__(self) -> None:
        self.now = datetime(2025, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def repository(clock: ManualClock | None = None) -> InMemoryPrivateKeyRepository:
    return InMemoryPrivateKeyRepository(
        encryption_key="test-encryption-key",
        clock=clock or ManualClock(),
    )


def test_create_private_key_stores_metadata_and_ts_style_prefix() -> None:
    repo = repository()

    key_value, private_key = repo.create(
        display_name="Connect Session",
        entity_type=PrivateKeyEntityType.CONNECT_SESSION,
        entity_id=10,
        account_id=20,
        environment_id=30,
    )

    assert key_value.startswith("nango_connect_session_")
    assert private_key.display_name == "Connect Session"
    assert private_key.entity_type == PrivateKeyEntityType.CONNECT_SESSION
    assert private_key.expires_at is None
    assert private_key.last_access_at is None
    assert private_key.encrypted is None


def test_lookup_by_key_hash_returns_private_key() -> None:
    repo = repository()
    key_value, private_key = repo.create(
        display_name="Connection",
        entity_type=PrivateKeyEntityType.CONNECTION,
        entity_id=1,
        account_id=2,
        environment_id=3,
    )
    key_hash = hash_private_key_value(key_value, "test-encryption-key")

    found = repo.get_by_hash(key_hash)

    assert found == private_key


def test_hash_matches_ts_pbkdf2_fixture() -> None:
    assert (
        hash_private_key_value("nango_connect_session_abcdef", "test-encryption-key")
        == "MboriZDg73s23cGPxPk+rOLeyMzd3kq1qSjrOLJVQtQ="
    )


def test_expired_private_key_cannot_be_found() -> None:
    clock = ManualClock()
    repo = repository(clock)
    key_value, _private_key = repo.create(
        display_name="Environment",
        entity_type=PrivateKeyEntityType.ENVIRONMENT,
        entity_id=1,
        account_id=2,
        environment_id=3,
        ttl_ms=100,
    )
    clock.advance(timedelta(milliseconds=101))

    with pytest.raises(PrivateKeyNotFoundError):
        repo.get(key_value)


def test_delete_removes_private_key() -> None:
    repo = repository()
    key_value, _private_key = repo.create(
        display_name="Connection",
        entity_type=PrivateKeyEntityType.CONNECTION,
        entity_id=1,
        account_id=2,
        environment_id=3,
    )

    repo.delete(key_value=key_value, entity_type=PrivateKeyEntityType.CONNECTION)

    with pytest.raises(PrivateKeyNotFoundError):
        repo.get(key_value)


def test_lookup_updates_last_access_at() -> None:
    clock = ManualClock()
    repo = repository(clock)
    key_value, private_key = repo.create(
        display_name="Connection",
        entity_type=PrivateKeyEntityType.CONNECTION,
        entity_id=1,
        account_id=2,
        environment_id=3,
    )
    clock.advance(timedelta(seconds=5))

    found = repo.get(key_value)

    assert private_key.last_access_at is None
    assert found.last_access_at == clock.now
