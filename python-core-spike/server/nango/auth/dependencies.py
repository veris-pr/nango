from __future__ import annotations

from typing import Annotated, Protocol, cast

from fastapi import Depends, Header, HTTPException, Request

from nango.auth.models import AccountContext
from nango.auth.service import AuthService
from nango.persist.models import PersistAuthContext


class AuthResolver(Protocol):
    async def get_account_context_by_api_key(
        self,
        *,
        secret_key: str | None = None,
        internal_secret_key: str | None = None,
    ) -> AccountContext | None: ...


def auth_service(request: Request) -> AuthResolver:
    service = getattr(request.app.state, "auth_service", None)
    if service is not None and hasattr(service, "get_account_context_by_api_key"):
        return cast(AuthResolver, service)

    session_factory = getattr(request.app.state, "db_session_factory", None)
    settings = getattr(request.app.state, "settings", None)
    return AuthService(session_factory=session_factory, settings=settings)


async def api_auth(
    request: Request,
    service: Annotated[AuthResolver, Depends(auth_service)],
    authorization: str | None = Header(default=None),
    nango_is_script: str | None = Header(default=None, alias="Nango-Is-Script"),
) -> AccountContext:
    secret = _bearer_token(authorization)
    context = await service.get_account_context_by_api_key(
        internal_secret_key=secret if nango_is_script == "true" else None,
        secret_key=None if nango_is_script == "true" else secret,
    )
    if context is None:
        raise _auth_error("unauthorized", "Unauthorized: Account not found")
    return context


async def persist_auth(
    environment_id: int,
    service: Annotated[AuthResolver, Depends(auth_service)],
    authorization: str | None = Header(default=None),
) -> PersistAuthContext:
    secret = _bearer_token(authorization)
    context = await service.get_account_context_by_api_key(internal_secret_key=secret)
    if context is None:
        return PersistAuthContext(environment_id=environment_id, token=secret)
    if context.environment.id != environment_id:
        raise _auth_error("unauthorized", "Unauthorized: Matching environment not found")
    return PersistAuthContext(
        environment_id=context.environment.id,
        token=secret,
        account_id=context.account.id,
    )


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise _auth_error("missing_auth_header", "Missing authorization header")

    prefix = "Bearer "
    if not authorization.startswith(prefix) or authorization == prefix:
        raise _auth_error(
            "malformed_auth_header",
            "Malformed authorization header. Expected `Bearer SECRET_KEY`",
        )

    return authorization.removeprefix(prefix)


def _auth_error(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"error": {"code": code, "message": message}})
