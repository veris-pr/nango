"""Keystore application port: PrivateKeyRepository protocol."""

from __future__ import annotations

from typing import Protocol

from nango_py.keystore.domain.private_key import PrivateKey, PrivateKeyEntityType


class PrivateKeyRepository(Protocol):
    async def create_private_key(
        self,
        *,
        display_name: str,
        entity_type: PrivateKeyEntityType,
        entity_id: int,
        account_id: int,
        environment_id: int,
        ttl_ms: int | None = None,
    ) -> tuple[str, PrivateKey]: ...

    async def get_private_key(self, key_value: str) -> PrivateKey | None: ...

    async def delete_private_key(
        self, *, key_value: str, entity_type: PrivateKeyEntityType
    ) -> bool: ...