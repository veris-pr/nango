"""Auth domain model.

Plain frozen dataclasses. No Pydantic, FastAPI, or SQLAlchemy here — those
live at the transport and infrastructure boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

AuthSource = Literal["customer_key", "api_secret", "env_var"]


@dataclass(frozen=True)
class Account:
    id: int
    name: str
    uuid: str | None = None


@dataclass(frozen=True)
class Environment:
    id: int
    name: str
    account_id: int
    uuid: str
    is_production: bool = False


@dataclass(frozen=True)
class ApiSecret:
    id: int
    environment_id: int
    display_name: str
    secret: str
    hashed: str
    is_default: bool


@dataclass(frozen=True)
class Scopes:
    """Granted API-key scopes with TypeScript wildcard semantics.

    Mirrors ``hasScope`` in ``packages/server/lib/middleware/scope.middleware.ts``:
    an exact match wins, and a scope ending in ``:*`` matches any required
    scope that starts with the prefix before ``*``.
    """

    granted: tuple[str, ...] = field(default=())

    def has(self, required: str) -> bool:
        for scope in self.granted:
            if scope == required:
                return True
            if scope.endswith(":*") and required.startswith(scope[:-1]):
                return True
        return False

    def has_any(self, required: tuple[str, ...]) -> bool:
        return any(self.has(scope) for scope in required)


@dataclass(frozen=True)
class AuthenticatedContext:
    account: Account
    environment: Environment
    secret: ApiSecret
    auth_source: AuthSource
    scopes: Scopes
    api_key_id: int | None = None