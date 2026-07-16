"""Connections domain model.

Plain frozen dataclasses. ``credentials`` is the decrypted credentials dict
(``AllAuthCredentials``) carried as an opaque mapping; only the read-side
transform (refresh_token stripping) inspects its shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ConnectionEndUserOrganization:
    id: str
    display_name: str | None = None


@dataclass(frozen=True)
class ConnectionEndUser:
    id: str
    email: str | None = None
    display_name: str | None = None
    tags: JsonObject | None = None
    organization: ConnectionEndUserOrganization | None = None


@dataclass(frozen=True)
class ConnectionActiveLog:
    type: str
    log_id: str


@dataclass(frozen=True)
class Connection:
    """Decrypted connection row joined with end_user, active_logs, and provider."""

    id: int
    connection_id: str
    provider_config_key: str
    provider: str
    environment_id: int
    config_id: int | None
    tags: JsonObject
    metadata: JsonObject | None
    connection_config: JsonObject
    credentials: JsonObject
    last_fetched_at: datetime | None
    created_at: datetime
    updated_at: datetime
    end_user: ConnectionEndUser | None = None
    active_logs: list[ConnectionActiveLog] = field(default_factory=list)


@dataclass(frozen=True)
class ConnectionListItem:
    """ApiPublicConnection — list response item (no credentials)."""

    id: int
    connection_id: str
    provider_config_key: str
    provider: str
    errors: list[ConnectionActiveLog]
    end_user: ConnectionEndUser | None
    tags: JsonObject
    metadata: JsonObject | None
    created: str  # ISO 8601


@dataclass(frozen=True)
class ConnectionFull:
    """ApiPublicConnectionFull — single response (top-level object)."""

    id: int
    connection_id: str
    provider_config_key: str
    provider: str
    errors: list[ConnectionActiveLog]
    end_user: ConnectionEndUser | None
    tags: JsonObject
    metadata: JsonObject | None
    connection_config: JsonObject
    created_at: str
    updated_at: str
    last_fetched_at: str | None
    credentials: JsonObject