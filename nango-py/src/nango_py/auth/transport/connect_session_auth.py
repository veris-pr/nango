"""Connect-session-or-API-key and connect-session-or-public-key auth dependencies.

Mirrors ``connectSessionOrSecretKeyAuth`` and ``connectSessionOrPublicKeyAuth``
in ``packages/server/lib/middleware/access.middleware.ts``.

``connect_session_or_api_auth``: tries connect session token (Bearer) first;
if that fails and the token doesn't start with ``nango_connect_session_``,
falls back to API key auth. Used by ``/providers``, ``/integrations`` (list).

``connect_session_or_public_auth``: checks ``connect_session_token`` query
param first; if absent, checks ``public_key`` query param. Used by auth flow
endpoints (``/api-auth/*``, ``/auth/*``, ``/oauth/*``, ``/app-store-auth/*``).
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import Header, Query, Request

from nango_py.auth.domain.context import (
    Account,
    ApiSecret,
    AuthenticatedContext,
    Environment,
    Scopes,
)
from nango_py.auth.domain.errors import (
    InvalidSecretKeyFormat,
    MalformedAuthHeader,
    MissingAuthHeader,
    UnknownAccount,
)
from nango_py.keystore.application.gateway import PrivateKeyRepository
from nango_py.shared.errors import ApiError

_CONNECT_SESSION_TOKEN_PREFIX = "nango_connect_session_"
_CONNECT_SESSION_SCOPES = Scopes((
    "environment:integrations:list",
    "environment:integrations:list_credentials",
    "environment:connect_sessions:write",
    "environment:connections:write",
    "environment:proxy",
))
_UUID_V4 = re.compile(
    r"^[0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$",
    re.IGNORECASE,
)


async def connect_session_or_api_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthenticatedContext:
    """``connectSessionOrSecretKeyAuth`` — connect session OR API key (Bearer).

    Tries connect session token first; if it fails and the token doesn't start
    with the connect session prefix, falls back to regular API key auth.
    """
    if authorization is None:
        raise MissingAuthHeader()

    token = _bearer_token(authorization)
    if token is None or token == "":
        raise MalformedAuthHeader()

    # Try connect session first
    keystore = getattr(request.app.state, "private_key_repo", None)
    session_repo = getattr(request.app.state, "connect_session_repo", None)
    if keystore is not None and session_repo is not None:
        cs_context = await _try_connect_session(keystore, session_repo, token)
        if cs_context is not None:
            request.state.connect_session_id = cs_context[1]
            return cs_context[0]

    # If token starts with connect session prefix, don't fall back to API key
    if token.startswith(_CONNECT_SESSION_TOKEN_PREFIX):
        raise UnknownAccount()

    # Fall back to API key auth (inline — mirrors api_auth logic)
    if not _UUID_V4.fullmatch(token):
        raise InvalidSecretKeyFormat()

    auth_gateway = getattr(request.app.state, "auth_gateway", None)
    if auth_gateway is None:
        raise UnknownAccount()

    is_script = request.headers.get("nango-is-script") == "true"
    if is_script:
        context = await auth_gateway.resolve_by_internal_secret_key(token)
    else:
        context = await auth_gateway.resolve_by_secret_key(token)
    if context is None:
        raise UnknownAccount()
    return context  # type: ignore[no-any-return]


async def connect_session_or_public_auth(
    request: Request,
    connect_session_token: str | None = Query(default=None, alias="connect_session_token"),
    public_key: str | None = Query(default=None, alias="public_key"),
) -> AuthenticatedContext:
    """``connectSessionOrPublicKeyAuth`` — connect session OR public key (query).

    Checks ``connect_session_token`` query param first; if absent, checks
    ``public_key`` query param. Used by auth flow endpoints.
    """
    if connect_session_token is not None:
        keystore = getattr(request.app.state, "private_key_repo", None)
        session_repo = getattr(request.app.state, "connect_session_repo", None)
        if keystore is not None and session_repo is not None:
            cs_context = await _try_connect_session(keystore, session_repo, connect_session_token)
            if cs_context is not None:
                request.state.connect_session_id = cs_context[1]
                return cs_context[0]
        raise UnknownAccount()

    if public_key is not None:
        if not _UUID_V4.fullmatch(public_key):
            raise _invalid_public_key()
        # Look up environment by public_key
        auth_gateway = getattr(request.app.state, "auth_gateway", None)
        if auth_gateway is not None:
            context = await _resolve_public_key(auth_gateway, public_key)
            if context is not None:
                return context
        raise UnknownAccount()

    raise _missing_public_key()


async def _try_connect_session(
    keystore: PrivateKeyRepository,
    session_repo: Any,
    token: str,
) -> tuple[AuthenticatedContext, int] | None:
    """Validate a connect session token and return (context, session_id)."""
    private_key = await keystore.get_private_key(token)
    if private_key is None:
        return None

    session = await session_repo.get_by_id(
        id=private_key.entity_id,
        account_id=private_key.account_id,
        environment_id=private_key.environment_id,
    )
    if session is None:
        return None

    # Resolve account + environment from the session
    return (
        AuthenticatedContext(
            account=Account(id=private_key.account_id, name=""),
            environment=Environment(
                id=private_key.environment_id,
                name="",
                account_id=private_key.account_id,
                uuid="",
            ),
            secret=ApiSecret(
                id=0,
                environment_id=private_key.environment_id,
                display_name="",
                secret="",
                hashed="",
                is_default=True,
            ),
            auth_source="env_var",
            scopes=_CONNECT_SESSION_SCOPES,
        ),
        session.id,
    )


async def _resolve_public_key(
    auth_gateway: Any,
    public_key: str,
) -> AuthenticatedContext | None:
    """Resolve an environment by public key via the auth gateway.

    Mirrors ``getAccountContextByPublicKey`` — calls
    ``auth_gateway.resolve_by_public_key(public_key)``.
    """
    resolve = getattr(auth_gateway, "resolve_by_public_key", None)
    if resolve is None:
        return None
    return await resolve(public_key)  # type: ignore[no-any-return]


def _bearer_token(authorization: str) -> str | None:
    if not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    return token if token else None


def _missing_public_key() -> ApiError:
    class _Err(ApiError):
        status = 401
        code = "missing_public_key"
        message = "Authentication failed. The request is missing a valid public key parameter."

    return _Err()


def _invalid_public_key() -> ApiError:
    class _Err(ApiError):
        status = 401
        code = "invalid_public_key"
        message = "Authentication failed. The provided public key is not a UUID v4."

    return _Err()