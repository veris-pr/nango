"""FastAPI dependency: resolve an :class:`AuthenticatedContext` from a request.

Mirrors ``packages/server/lib/middleware/access.middleware.ts`` ``secretKeyAuth``:
- missing Authorization header -> ``missing_auth_header``
- ``Bearer `` split yields empty token -> ``malformed_auth_header``
- token not UUID v4 -> ``invalid_secret_key_format``
- no matching account -> ``unknown_account``
- ``Nango-Is-Script: true`` routes the token through the internal-secret path.
"""

from __future__ import annotations

import re
from functools import lru_cache

from fastapi import Request

from nango_py.auth.application.gateway import AuthGateway
from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.domain.errors import (
    InvalidSecretKeyFormat,
    MalformedAuthHeader,
    MissingAuthHeader,
    UnknownAccount,
)

_BEARER_PREFIX = "Bearer "
# UUID v4, case-insensitive — mirrors keyRegex in access.middleware.ts.
_UUID_V4 = re.compile(
    r"^[0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _compiled_uuid() -> re.Pattern[str]:
    return _UUID_V4


def _bearer_token(authorization: str | None) -> str | None:
    """Return the token after ``Bearer ``, or None if the header is malformed.

    Mirrors ``authorizationHeader.split('Bearer ').pop()``: a header without the
    ``Bearer `` prefix yields the whole string (which then fails the UUID check),
    and ``Bearer `` with no token yields an empty string -> malformed.
    """
    if authorization is None:
        return None
    parts = authorization.split(_BEARER_PREFIX)
    return parts[-1]


async def api_auth(request: Request) -> AuthenticatedContext:
    gateway: AuthGateway = request.app.state.auth_gateway

    authorization = request.headers.get("authorization")
    if authorization is None:
        raise MissingAuthHeader()

    token = _bearer_token(authorization)
    if token is None or token == "":
        raise MalformedAuthHeader()
    if not _compiled_uuid().fullmatch(token):
        raise InvalidSecretKeyFormat()

    is_script = request.headers.get("nango-is-script") == "true"
    if is_script:
        context = await gateway.resolve_by_internal_secret_key(token)
    else:
        context = await gateway.resolve_by_secret_key(token)
    if context is None:
        raise UnknownAccount()
    return context


_CONNECT_SESSION_TOKEN_PREFIX = "nango_connect_session_"


async def connect_session_auth(request: Request) -> AuthenticatedContext:
    """Resolve auth from a connect session token (Bearer nango_connect_session_*).

    Mirrors ``connectSessionAuth`` in access.middleware.ts — the token is a
    connect session token, not a secret key. The gateway resolves it to a
    minimal AuthenticatedContext (environment + account, no scopes).
    """
    gateway: AuthGateway = request.app.state.auth_gateway

    authorization = request.headers.get("authorization")
    if authorization is None:
        raise MissingAuthHeader()

    token = _bearer_token(authorization)
    if token is None or token == "":
        raise MalformedAuthHeader()

    if not token.startswith(_CONNECT_SESSION_TOKEN_PREFIX):
        raise MalformedAuthHeader()

    context = await gateway.resolve_by_connect_session_token(token)
    if context is None:
        raise UnknownAccount()
    return context