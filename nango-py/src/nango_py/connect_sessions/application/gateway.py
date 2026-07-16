"""Connect session repository protocol."""

from __future__ import annotations

from typing import Protocol

from nango_py.connect_sessions.domain.session import ConnectSession


class ConnectSessionRepository(Protocol):
    async def create(
        self,
        *,
        account_id: int,
        environment_id: int,
        allowed_integrations: list[str] | None,
        integrations_config_defaults: dict[str, object] | None,
        end_user: dict[str, object] | None,
        tags: dict[str, str],
        overrides: dict[str, object] | None,
    ) -> ConnectSession: ...

    async def get_by_id(
        self, *, id: int, account_id: int, environment_id: int
    ) -> ConnectSession | None: ...

    async def delete(self, *, id: int, account_id: int, environment_id: int) -> bool: ...