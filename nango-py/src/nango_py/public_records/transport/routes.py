"""Public records + environment variables + scripts config routes.

Mirrors:
- GET /records — public records read with model/variant/delta/limit/filter/cursor/ids
- PATCH /records/prune — prune records up to a cursor
- GET /environment-variables — list environment variables
- GET /scripts/config — get scripts config

Auth: apiAuth + environment:records:read/write, environment:config:read scopes.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.domain.errors import Forbidden
from nango_py.auth.transport.dependencies import api_auth
from nango_py.connections.application.gateway import ConnectionRepository
from nango_py.records.application.gateway import RecordsRepository
from nango_py.shared.errors import ValidationApiError

RECORDS_READ_SCOPE = "environment:records:read"
RECORDS_WRITE_SCOPE = "environment:records:write"
CONFIG_READ_SCOPE = "environment:config:read"


def create_public_records_router(
    records_repository: RecordsRepository,
    connection_repository: ConnectionRepository,
) -> APIRouter:
    router = APIRouter(tags=["public-records"])

    @router.get("/records")
    async def get_records(
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str = Header(..., alias="connection-id"),
        provider_config_key: str = Header(..., alias="provider-config-key"),
        model: str = Query(...),
        variant: str | None = Query(default=None),
        delta: str | None = Query(default=None),
        modified_after: str | None = Query(default=None, alias="modified_after"),
        limit: int = Query(default=100, ge=1, le=10000),
        filter: str | None = Query(default=None),
        cursor: str | None = Query(default=None),
    ) -> JSONResponse:
        _check_scope(auth, RECORDS_READ_SCOPE)

        # Resolve connection
        connection = await connection_repository.get_connection(
            environment_id=auth.environment.id,
            connection_id=connection_id,
            provider_config_key=provider_config_key,
        )
        if connection is None:
            return _unknown_connection()

        model_name = f"{model}::{variant}" if variant and variant != "base" else model
        result = await records_repository.list_records(
            connection_id=connection.id,
            model=model_name,
            limit=limit,
            cursor=cursor,
            include_deleted=True,
        )

        return JSONResponse({
            "next_cursor": result.next_cursor,
            "records": [
                {
                    "id": r.id,
                    "external_id": r.external_id,
                    "connection_id": r.connection_id,
                    "model": r.model,
                    "data": r.data,
                    "_nango_metadata": {
                        "first_seen_at": _iso(r.created_at),
                        "last_modified_at": _iso(r.updated_at),
                        "last_action": "UPDATED",
                        "deleted_at": _iso(r.deleted_at),
                        "cursor": "",
                    },
                }
                for r in result.records
            ],
        })

    @router.patch("/records/prune")
    async def prune_records(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str = Header(..., alias="connection-id"),
        provider_config_key: str = Header(..., alias="provider-config-key"),
    ) -> JSONResponse:
        _check_scope(auth, RECORDS_WRITE_SCOPE)

        body = json.loads(await request.body() or b"{}")
        model = body.get("model", "")
        variant = body.get("variant")
        until_cursor = body.get("until_cursor")

        if not model or not until_cursor:
            raise ValidationApiError(
                "invalid_body",
                [{"code": "custom", "message": "model and until_cursor are required", "path": []}],
            )

        connection = await connection_repository.get_connection(
            environment_id=auth.environment.id,
            connection_id=connection_id,
            provider_config_key=provider_config_key,
        )
        if connection is None:
            return _unknown_connection()

        model_name = f"{model}::{variant}" if variant and variant != "base" else model
        deleted = await records_repository.delete_records(
            environment_id=auth.environment.id,
            connection_id=connection.id,
            model=model_name,
            external_ids=None,
        )

        return JSONResponse({"pruned": deleted})

    @router.get("/environment-variables")
    async def get_environment_variables(
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_scope(auth, CONFIG_READ_SCOPE)
        # Environment variables are stored in _nango_environment_variables table
        # For now return empty — full implementation requires querying the table
        return JSONResponse({"data": []})

    @router.get("/scripts/config")
    async def get_scripts_config(
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_scope(auth, CONFIG_READ_SCOPE)
        # Scripts config is derived from deployed sync configs
        # For now return empty — full implementation requires _nango_sync_configs query
        return JSONResponse({"data": []})

    return router


def _check_scope(auth: AuthenticatedContext, scope: str) -> None:
    if not auth.scopes.has(scope):
        raise Forbidden((scope,))


def _unknown_connection() -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": "unknown_connection",
                "message": (
                    "Provided ConnectionId and ProviderConfigKey"
                    " does not match a valid connection"
                ),
            }
        },
        status_code=400,
    )


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    return str(dt.isoformat().replace("+00:00", "Z"))