"""Connect session domain model and errors.

Mirrors ``ConnectSession`` in ``packages/types/lib/connect/session.ts`` and
``ConnectSessionError`` in
``packages/server/lib/services/connectSession.service.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ConnectSession:
    id: int
    end_user_id: int | None
    account_id: int | None
    environment_id: int | None
    allowed_integrations: tuple[str, ...] | None
    integrations_config_defaults: JsonObject | None
    connection_id: int | None
    operation_id: str | None
    overrides: JsonObject | None
    end_user: JsonObject | None
    tags: dict[str, str]
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class CreateConnectSessionResult:
    token: str
    connect_link: str
    expires_at: str  # ISO 8601


@dataclass(frozen=True)
class ConnectSessionData:
    """Response for GET /connect/session (minus connectUISettings, deferred)."""

    end_user: JsonObject | None
    allowed_integrations: tuple[str, ...] | None
    integrations_config_defaults: JsonObject | None
    is_reconnecting: bool
    overrides: JsonObject | None