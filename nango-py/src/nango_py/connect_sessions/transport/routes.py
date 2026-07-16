"""FastAPI router for connect sessions.

POST /connect/sessions, GET /connect/session, DELETE /connect/session.

Authoritative behavior:
``packages/server/lib/controllers/connect/postSessions.ts``,
``packages/server/lib/controllers/connect/getSession.ts``,
``packages/server/lib/controllers/connect/deleteSession.ts``.

connectUISettings is deferred (returns empty defaults). Integration existence
validation (allowedIntegrations/integrationsConfigDefaults/overrides) is deferred
to a follow-up; Phase 5a focuses on the core create/get/delete token flow.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, Response

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.domain.errors import MalformedAuthHeader, MissingAuthHeader
from nango_py.auth.transport.dependencies import api_auth, connect_session_auth
from nango_py.connect_sessions.application.use_cases import (
    CreateConnectSession,
    CreateConnectSessionRequest,
    DeleteConnectSession,
    GetConnectSessionByToken,
)
from nango_py.contracts.connect import ConnectSessionCreateRequest
from nango_py.shared.errors import ApiError

_CONNECT_SESSION_TOKEN_PREFIX = "nango_connect_session_"
CONNECT_URL_DEFAULT = "https://connect.nango.dev"


def create_connect_sessions_router(
    create_session: CreateConnectSession,
    get_session: GetConnectSessionByToken,
    delete_session: DeleteConnectSession,
) -> APIRouter:
    router = APIRouter(tags=["connect-sessions"])

    @router.post("/connect/sessions", status_code=201)
    async def create_connect_session_route(
        request_body: ConnectSessionCreateRequest,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        result = await create_session.execute(
            CreateConnectSessionRequest(
                context=auth,
                end_user=_to_dict(request_body.end_user),
                organization=_to_dict(request_body.organization),
                allowed_integrations=request_body.allowed_integrations,
                integrations_config_defaults=_config_defaults(request_body),
                overrides=_to_dict(request_body.overrides) if request_body.overrides else None,
                tags=request_body.tags,
            )
        )
        return JSONResponse(
            {
            "data": {
                "token": result.token,
                "connect_link": result.connect_link,
                "expires_at": result.expires_at,
            }
        },
            status_code=201,
        )

    @router.get("/connect/session")
    async def get_connect_session_route(
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        token = _bearer_token(authorization)
        data = await get_session.execute(token)
        if data is None:
            raise _connect_session_not_found()
        body: dict[str, Any] = {
            "endUser": _end_user_to_api(data.end_user),
        }
        if data.allowed_integrations is not None:
            body["allowed_integrations"] = list(data.allowed_integrations)
        if data.integrations_config_defaults is not None:
            body["integrations_config_defaults"] = data.integrations_config_defaults
        if data.is_reconnecting:
            body["isReconnecting"] = True
        if data.overrides is not None:
            body["overrides"] = data.overrides
        return JSONResponse({"data": body})

    @router.delete("/connect/session", status_code=204)
    async def delete_connect_session_route(
        authorization: str | None = Header(default=None),
    ) -> Response:
        token = _bearer_token(authorization)
        await delete_session.execute(token)
        return Response(status_code=204)

    @router.post("/connect/sessions/reconnect")
    async def reconnect_connect_session_route(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        body = json.loads(await request.body() or b"{}")
        connection_id = body.get("connection_id", "")
        integration_id = body.get("integration_id", "")
        if not connection_id or not integration_id:
            raise _invalid_body(
                "connection_id and integration_id are required"
            )
        # Reconnect creates a new connect session with is_reconnecting=True
        icd = body.get("integrations_config_defaults") or {}
        result = await create_session.execute(
            CreateConnectSessionRequest(
                context=auth,
                end_user=_to_dict(body.get("end_user")),
                organization=_to_dict(body.get("organization")),
                allowed_integrations=[integration_id] if integration_id else None,
                integrations_config_defaults=icd or None,
                overrides=_to_dict(body.get("overrides")),
                tags=body.get("tags"),
            )
        )
        return JSONResponse(
            {
                "data": {
                    "token": result.token,
                    "connect_link": result.connect_link,
                    "expires_at": result.expires_at,
                }
            },
            status_code=201,
        )

    @router.post("/connect/telemetry")
    async def connect_telemetry_route(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(connect_session_auth)],
    ) -> JSONResponse:
        await request.body()
        # Telemetry is fire-and-forget; just acknowledge
        return JSONResponse({"success": True})

    return router


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise _missing_auth()
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise _malformed_auth()
    token = authorization.removeprefix(prefix).strip()
    if not token:
        raise _malformed_auth()
    return token


def _to_dict(obj: Any) -> dict[str, Any] | None:
    if obj is None:
        return None
    return (
        obj.model_dump(by_alias=True, exclude_none=True)
        if hasattr(obj, "model_dump")
        else dict(obj)
    )


def _config_defaults(request_body: ConnectSessionCreateRequest) -> dict[str, Any] | None:
    if request_body.integrations_config_defaults is None:
        return None
    result: dict[str, Any] = {}
    for key, defaults in request_body.integrations_config_defaults.items():
        result[key] = {
            "user_scopes": defaults.user_scopes,
            "authorization_params": defaults.authorization_params,
            "connectionConfig": defaults.connection_config,
        }
    return result


def _end_user_to_api(end_user: dict[str, Any] | None) -> dict[str, Any] | None:
    if end_user is None:
        return None
    return {
        "id": end_user.get("end_user_id") or end_user.get("id"),
        "display_name": end_user.get("display_name") or None,
        "email": end_user.get("email") or None,
        "tags": end_user.get("tags") or None,
        "organization": {
            "id": end_user.get("organization_id"),
            "display_name": end_user.get("organization_display_name") or None,
        }
        if end_user.get("organization_id")
        else None,
    }


def _missing_auth() -> MissingAuthHeader:
    return MissingAuthHeader()


def _malformed_auth() -> MalformedAuthHeader:
    return MalformedAuthHeader()


def _connect_session_not_found() -> ApiError:
    class _NotFound(ApiError):
        status = 404
        code = "not_found"
        message = "Connect session was not found or has expired"
    return _NotFound()


def _invalid_body(message: str) -> ApiError:
    class _Err(ApiError):
        status = 400
        code = "invalid_body"

    err = _Err()
    err.message = message
    return err


__all__: list[Any] = []