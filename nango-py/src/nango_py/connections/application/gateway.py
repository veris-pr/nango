"""Connections application ports.

The single connection read also needs an integration lookup (to surface
``unknown_provider_config`` before the connection lookup), so the
:class:`GetConnection` use case depends on :class:`IntegrationRepository`
from the integrations context.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from nango_py.connections.domain.connection import Connection


@dataclass(frozen=True)
class ListConnectionsFilters:
    environment_id: int
    connection_id: str | None = None
    integration_ids: tuple[str, ...] = ()
    search: str | None = None
    end_user_id: str | None = None
    end_user_organization_id: str | None = None
    tags: dict[str, str] | None = None
    limit: int = 10_000
    page: int = 0


class ConnectionRepository(Protocol):
    async def list_connections(self, filters: ListConnectionsFilters) -> list[Connection]: ...

    async def get_connection(
        self, *, environment_id: int, connection_id: str, provider_config_key: str
    ) -> Connection | None: ...

    async def update_credentials(
        self,
        *,
        connection_id: int,
        credentials: dict[str, object],
        expires_at: datetime | None,
    ) -> None: ...

    async def upsert_connection(
        self,
        *,
        environment_id: int,
        config_id: int,
        connection_id: str,
        provider_config_key: str,
        credentials: dict[str, object],
        connection_config: dict[str, object],
    ) -> tuple[int, str]: ...