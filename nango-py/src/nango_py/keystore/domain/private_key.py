"""PrivateKey domain model.

Mirrors ``PrivateKey`` in ``packages/keystore/lib/models/privatekeys.ts``.
``encrypted`` stores the AES-GCM ciphertext as ``b\"{ciphertext}:{iv}:{tag}\"``
(base64 components joined by ``:``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

PrivateKeyEntityType = Literal["connect_session", "connection", "environment"]


@dataclass(frozen=True)
class PrivateKey:
    id: int
    display_name: str
    account_id: int
    environment_id: int
    encrypted: bytes | None
    hash: str
    created_at: datetime
    expires_at: datetime | None
    last_access_at: datetime | None
    entity_type: PrivateKeyEntityType
    entity_id: int