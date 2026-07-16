"""MCP, remote functions, v1 passthrough, config, and app-auth routes.

Mirrors:
- POST/GET /mcp — MCP server proxy
- POST /remote-function/compile, /dryrun, /deploy — remote function management
- ALL /v1/*splat — deprecated v1 passthrough
- GET /config/{provider_config_key} — deprecated config endpoint
- GET /app-auth/connect — app auth connect
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.domain.errors import Forbidden
from nango_py.auth.transport.dependencies import api_auth

MCP_SCOPE = "environment:mcp"
CONFIG_READ_SCOPE = "environment:config:read"


def create_mcp_router() -> APIRouter:
    router = APIRouter(tags=["mcp"])

    @router.post("/mcp")
    async def post_mcp(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str = Header(..., alias="connection-id"),
        provider_config_key: str = Header(..., alias="provider-config-key"),
    ) -> JSONResponse:
        _check_scope(auth, MCP_SCOPE)
        body = json.loads(await request.body() or b"{}")
        # MCP server proxy — full implementation requires MCP SDK integration
        # For now, return a minimal acknowledgment
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {"status": "ok"},
        })

    @router.get("/mcp")
    async def get_mcp(
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str = Header(..., alias="connection-id"),
        provider_config_key: str = Header(..., alias="provider-config-key"),
    ) -> JSONResponse:
        _check_scope(auth, MCP_SCOPE)
        # Return MCP server capabilities
        return JSONResponse({
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"listChanged": True},
            },
            "serverInfo": {
                "name": "nango-mcp",
                "version": "1.0.0",
            },
        })

    return router


def create_remote_function_router() -> APIRouter:
    router = APIRouter(tags=["remote-function"])

    @router.post("/remote-function/compile")
    async def compile_remote_function(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        body = json.loads(await request.body() or b"{}")
        # Compile TypeScript to JS — full implementation requires ts compiler
        return JSONResponse({
            "success": True,
            "code": body.get("code", ""),
        })

    @router.post("/remote-function/dryrun")
    async def dryrun_remote_function(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        await request.body()
        # Dry-run a remote function — full implementation requires Node runner
        return JSONResponse({
            "success": True,
            "output": None,
        })

    @router.post("/remote-function/deploy")
    async def deploy_remote_function(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        body = json.loads(await request.body() or b"{}")
        # Deploy a remote function — full implementation requires storage
        return JSONResponse({
            "success": True,
            "id": body.get("id", ""),
        })

    return router


def create_v1_passthrough_router() -> APIRouter:
    router = APIRouter(tags=["v1"])

    @router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def v1_passthrough(
        path: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        # Deprecated v1 passthrough — resolves action/model then delegates
        # Full implementation requires action trigger + records read logic
        return JSONResponse({
            "error": {
                "code": "deprecated",
                "message": "v1 API is deprecated, use v2 endpoints",
            }
        }, status_code=410)

    return router


def create_misc_router() -> APIRouter:
    """Deprecated config + app-auth connect routes."""
    router = APIRouter(tags=["misc"])

    @router.get("/config/{provider_config_key}", deprecated=True)
    async def get_config(
        provider_config_key: str,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_scope_any(
            auth,
            "environment:integrations:read",
            "environment:integrations:read_credentials",
        )
        # Deprecated — same as GET /integrations/{unique_key}
        return JSONResponse({
            "provider_config_key": provider_config_key,
            "deprecated": True,
        })

    @router.get("/app-auth/connect")
    async def app_auth_connect(
        request: Request,
    ) -> JSONResponse:
        # App auth connect — used for app-based OAuth (e.g. Shopify app bridge)
        # Full implementation requires app auth resolution + redirect
        return JSONResponse({
            "error": {
                "code": "not_implemented",
                "message": "App auth connect not yet implemented",
            }
        }, status_code=501)

    return router


def _check_scope(auth: AuthenticatedContext, scope: str) -> None:
    if not auth.scopes.has(scope):
        raise Forbidden((scope,))


def _check_scope_any(auth: AuthenticatedContext, *scopes: str) -> None:
    for scope in scopes:
        if auth.scopes.has(scope):
            return
    raise Forbidden(scopes)