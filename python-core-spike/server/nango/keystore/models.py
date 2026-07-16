from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field

from nango.contracts.base import ContractModel


class PrivateKeyEntityType(StrEnum):
    CONNECT_SESSION = "connect_session"
    CONNECTION = "connection"
    ENVIRONMENT = "environment"


class PrivateKey(ContractModel):
    id: int
    display_name: str = Field(alias="displayName")
    account_id: int = Field(alias="accountId")
    environment_id: int = Field(alias="environmentId")
    encrypted: bytes | None = None
    hash: str
    created_at: datetime = Field(alias="createdAt")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
    last_access_at: datetime | None = Field(default=None, alias="lastAccessAt")
    entity_type: PrivateKeyEntityType = Field(alias="entityType")
    entity_id: int = Field(alias="entityId")

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at <= (now or datetime.now(UTC))
