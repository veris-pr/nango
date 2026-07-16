"""Auth application port.

The transport and use-case layers depend on this protocol. The SQLAlchemy
adapter in ``nango_py/auth/infrastructure`` implements it against the
``api_secrets`` / ``customer_keys`` / ``_nango_environments`` / ``_nango_accounts``
schemas produced by the authoritative Knex migrations.
"""

from __future__ import annotations

from typing import Protocol

from nango_py.auth.domain.context import AuthenticatedContext


class AuthGateway(Protocol):
    """Resolves an authenticated context from a presented secret key.

    Fail-closed: a missing or unmatched key returns ``None``; the caller maps
    that to ``UnknownAccount``. Malformed headers and non-UUID tokens are
    rejected before this gateway is reached (transport-layer concern).
    """

    async def resolve_by_secret_key(
        self, secret_key: str
    ) -> AuthenticatedContext | None: ...

    async def resolve_by_internal_secret_key(
        self, internal_secret_key: str
    ) -> AuthenticatedContext | None: ...

    async def resolve_by_public_key(
        self, public_key: str
    ) -> AuthenticatedContext | None: ...

    async def resolve_by_connect_session_token(
        self, token: str
    ) -> AuthenticatedContext | None: ...