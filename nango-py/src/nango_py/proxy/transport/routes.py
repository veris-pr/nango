"""FastAPI router for the proxy boundary.

``ANY /proxy/{path}`` — resolves connection, builds upstream request, executes
with retries, and passes the upstream response through (status + headers + body).

Authoritative behavior:
``packages/server/lib/controllers/proxy/allProxy.ts`` (``allPublicProxy``).

Credential refresh, TBA/OAUTH1 signing, multipart files, base_url_override
denylist, and header/body-based backoff waits are deferred. This Phase 4a path
covers the common auth modes (OAUTH2, API_KEY, BASIC, APP, OAUTH2_CC, JWT,
SIGNATURE, TWO_STEP) with exponential backoff retries.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.domain.errors import Forbidden
from nango_py.auth.transport.dependencies import api_auth
from nango_py.proxy.application.proxy_request import (
    ProxyRequest,
    ProxyRequestInput,
)
from nango_py.proxy.domain.errors import ProxyError
from nango_py.shared.errors import ValidationApiError

PROXY_SCOPE = "environment:proxy"
_PROXY_HEADER_PREFIX = "nango-proxy-"
_PROVIDER_CONFIG_KEY_RE = re.compile(r"^[a-zA-Z0-9~:.@ _-]+$")
_CONNECTION_ID_RE = re.compile(r"^[a-zA-Z0-9,.;:=+~[\]|@${}\"'\\/_ -]+$")
_RETRY_ON_RE = re.compile(r"^\d+(,\d+)*$")
_TRUTHY = {"true", "1", "yes", "on", "y", "enabled"}
_FALSY = {"false", "0", "no", "off", "n", "disabled"}
_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def create_proxy_router(proxy_request: ProxyRequest) -> APIRouter:
    router = APIRouter(tags=["proxy"])

    @router.api_route("/proxy/{path:path}", methods=_METHODS)
    async def proxy_route(
        path: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> Response:
        if not auth.scopes.has(PROXY_SCOPE):
            raise Forbidden((PROXY_SCOPE,))

        headers = _parse_proxy_headers(request)
        provider_config_key = _required_header(request, "provider-config-key")
        connection_id = _required_header(request, "connection-id")
        retries = _int_header(request, "retries", default=0, minimum=0)
        base_url_override = _str_header(request, "base-url-override", default=None)
        decompress = _bool_header(request, "decompress", default=False)
        retry_on = _retry_on_header(request)
        forward_headers_on_redirect = _bool_header(
            request, "forward-headers-on-redirect", default=True
        )

        body = await request.body()
        endpoint = "/" + path

        input_data = ProxyRequestInput(
            context=auth,
            connection_id=connection_id,
            provider_config_key=provider_config_key,
            method=request.method.upper(),
            endpoint=endpoint,
            forwarded_headers=headers,
            data=body if body else None,
            retries=retries,
            base_url_override=base_url_override,
            decompress=decompress,
            retry_on=retry_on,
            forward_headers_on_redirect=forward_headers_on_redirect,
        )

        client_kwargs: dict[str, Any] = {
            "follow_redirects": True,
            "timeout": httpx.Timeout(30.0, connect=10.0),
        }
        test_transport = getattr(request.app.state, "httpx_transport", None)
        if test_transport is not None:
            client_kwargs["transport"] = test_transport
        async with httpx.AsyncClient(**client_kwargs) as client:
            try:
                result = await proxy_request.execute(input_data, client)
            except ProxyError as exc:
                return JSONResponse(
                    exc.to_envelope(),
                    status_code=exc.status,
                )

        return Response(
            content=result.body,
            status_code=result.status,
            headers=result.headers,
        )

    return router


def _parse_proxy_headers(request: Request) -> dict[str, str]:
    """Extract Nango-Proxy-* forwarded headers (strip the prefix, lowercase)."""
    forwarded: dict[str, str] = {}
    for key, value in request.headers.items():
        if key.startswith(_PROXY_HEADER_PREFIX):
            forwarded[key.removeprefix(_PROXY_HEADER_PREFIX)] = value
    return forwarded


def _required_header(request: Request, name: str) -> str:
    value = request.headers.get(name)
    if not value:
        raise ValidationApiError(
            "invalid_headers",
            [{
                "code": "invalid_type",
                "message": f"Missing required header: {name}",
                "path": [name],
            }],
        )
    return value


def _str_header(request: Request, name: str, *, default: str | None) -> str | None:
    value = request.headers.get(name)
    if value is None or value == "":
        return default
    return value


def _int_header(
    request: Request, name: str, *, default: int, minimum: int = 0
) -> int:
    value = request.headers.get(name)
    if value is None or value == "":
        return default
    try:
        result = int(value)
    except ValueError:
        raise ValidationApiError(
            "invalid_headers",
            [{"code": "invalid_type", "message": f"{name} must be a number", "path": [name]}],
        ) from None
    if result < minimum:
        raise ValidationApiError(
            "invalid_headers",
            [{
                "code": "too_small",
                "message": f"{name} must be at least {minimum}",
                "path": [name],
            }],
        )
    return result


def _bool_header(request: Request, name: str, *, default: bool) -> bool:
    value = request.headers.get(name)
    if value is None or value == "":
        return default
    lowered = value.lower()
    if lowered in _TRUTHY:
        return True
    if lowered in _FALSY:
        return False
    raise ValidationApiError(
        "invalid_headers",
        [{"code": "invalid_string", "message": f"{name} must be a boolean string", "path": [name]}],
    )


def _retry_on_header(request: Request) -> tuple[int, ...]:
    value = request.headers.get("retry-on")
    if value is None or value == "":
        return ()
    if not _RETRY_ON_RE.fullmatch(value):
        raise ValidationApiError(
            "invalid_headers",
            [{
                "code": "invalid_string",
                "message": "retry-on must be comma-separated integers",
                "path": ["retry-on"],
            }],
        )
    return tuple(int(code) for code in value.split(","))


__all__: list[Any] = []