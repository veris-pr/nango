"""Integrations application ports.

Protocols only. Implementations live in ``nango_py/integrations/infrastructure``
(SQLAlchemy repository, provider YAML catalog).
"""

from __future__ import annotations

from typing import Protocol

from nango_py.integrations.domain.integration import Integration
from nango_py.integrations.domain.provider import Provider


class IntegrationRepository(Protocol):
    """Loads integration config rows from ``_nango_configs``."""

    async def get_by_unique_key(
        self, *, environment_id: int, unique_key: str
    ) -> Integration | None: ...

    async def list_for_environment(self, *, environment_id: int) -> list[Integration]: ...


class ProviderCatalog(Protocol):
    """In-memory lookup over the loaded providers.yaml catalog."""

    def get(self, name: str) -> Provider | None: ...

    def entry(self, name: str) -> dict[str, object] | None: ...

    def entries(self) -> dict[str, dict[str, object]]: ...