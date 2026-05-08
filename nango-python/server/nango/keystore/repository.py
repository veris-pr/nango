from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from nango.keystore.crypto import generate_private_key_value, hash_private_key_value
from nango.keystore.models import PrivateKey, PrivateKeyEntityType


def utc_now() -> datetime:
    return datetime.now(UTC)


class PrivateKeyError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PrivateKeyNotFoundError(PrivateKeyError):
    def __init__(self) -> None:
        super().__init__("not_found", "Private key not found")


class InMemoryPrivateKeyRepository:
    def __init__(self, *, encryption_key: str, clock: Callable[[], datetime] = utc_now) -> None:
        self._encryption_key = encryption_key
        self._clock = clock
        self._next_id = 1
        self._keys_by_hash: dict[str, PrivateKey] = {}

    def create(
        self,
        *,
        display_name: str,
        entity_type: PrivateKeyEntityType,
        entity_id: int,
        account_id: int,
        environment_id: int,
        ttl_ms: int | None = None,
        only_store_hash: bool = True,
    ) -> tuple[str, PrivateKey]:
        now = self._clock()
        key_value = generate_private_key_value(entity_type.value)
        key_hash = hash_private_key_value(key_value, self._encryption_key)
        private_key = PrivateKey(
            id=self._next_id,
            displayName=display_name,
            accountId=account_id,
            environmentId=environment_id,
            encrypted=None if only_store_hash else self._encrypted_value_placeholder(key_value),
            hash=key_hash,
            createdAt=now,
            expiresAt=self._expires_at(now, ttl_ms),
            lastAccessAt=None,
            entityType=entity_type,
            entityId=entity_id,
        )
        self._next_id += 1
        self._keys_by_hash[key_hash] = private_key
        return key_value, private_key

    def get(self, key_value: str) -> PrivateKey:
        key_hash = hash_private_key_value(key_value, self._encryption_key)
        private_key = self.get_by_hash(key_hash)
        now = self._clock()
        updated = private_key.model_copy(update={"last_access_at": now})
        self._keys_by_hash[key_hash] = updated
        return updated

    def get_by_hash(self, key_hash: str) -> PrivateKey:
        private_key = self._keys_by_hash.get(key_hash)
        if private_key is None or private_key.is_expired(self._clock()):
            self._keys_by_hash.pop(key_hash, None)
            raise PrivateKeyNotFoundError()
        return private_key

    def delete(self, *, key_value: str, entity_type: PrivateKeyEntityType) -> None:
        key_hash = hash_private_key_value(key_value, self._encryption_key)
        private_key = self._keys_by_hash.get(key_hash)
        if private_key is None or private_key.entity_type != entity_type:
            raise PrivateKeyNotFoundError()
        self._keys_by_hash.pop(key_hash)

    def delete_expired(self, *, limit: int, older_than_days: int) -> int:
        threshold = self._clock() - timedelta(days=older_than_days)
        expired_hashes = [
            key_hash
            for key_hash, private_key in self._keys_by_hash.items()
            if private_key.expires_at is not None and private_key.expires_at <= threshold
        ][:limit]
        for key_hash in expired_hashes:
            self._keys_by_hash.pop(key_hash, None)
        return len(expired_hashes)

    def _expires_at(self, now: datetime, ttl_ms: int | None) -> datetime | None:
        if ttl_ms is None or ttl_ms <= 0:
            return None
        return now + timedelta(milliseconds=ttl_ms)

    def _encrypted_value_placeholder(self, key_value: str) -> bytes:
        raise NotImplementedError(
            "Encrypted private key storage needs a TS compatibility fixture before Python parity."
        )
