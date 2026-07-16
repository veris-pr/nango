"""FastAPI router for the connection-read boundary.

Owns transport concerns only: auth dependency, query/param validation (strict,
matching the TypeScript zod ``.strict()`` schemas), and response serialization.

Authoritative behavior:
``packages/server/lib/controllers/connection/getConnections.ts``,
``packages/server/lib/controllers/connection/connectionId/getConnection.ts``.

Tag validation mirrors ``packages/shared/lib/services/tags/schema.ts``
(``connectionTagsKeySchema``, max 10 keys, lowercase normalization). The
``end_user_email`` email-format edge check is deferred (rare).
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.transport.dependencies import api_auth
from nango_py.connections.application.crud import (
    ConnectionCrudService,
    CreateConnectionRequest,
    DeleteConnectionRequest,
    PatchConnectionRequest,
    SetMetadataRequest,
)
from nango_py.connections.application.get_connection import (
    GetConnection,
    GetConnectionRequest,
)
from nango_py.connections.application.list_connections import (
    ListConnections,
    ListConnectionsRequest,
)
from nango_py.connections.transport.serialize import full_to_dict, serialize_list
from nango_py.shared.errors import ValidationApiError

# connectionIdSchema in packages/server/lib/helpers/validation.ts.
_CONNECTION_ID_RE = re.compile(r"^[a-zA-Z0-9,.;:=+~[\]|@${}\"'\\/_ -]+$")
_CONNECTION_ID_MAX = 255
# providerConfigKeySchema.
_PROVIDER_CONFIG_KEY_RE = re.compile(r"^[a-zA-Z0-9~:.@ _-]+$")
# connectionTagsKeySchema in packages/shared/lib/services/tags/schema.ts.
_TAG_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-./]*$")
_TAG_KEY_MAX = 64
_TAG_VALUE_MAX = 255
_TAG_MAX_COUNT = 10
_LIST_LIMIT_MAX = 2000
_LIST_LIMIT_DEFAULT = 10_000
_TRUTHY = {"true", "1", "yes", "on", "y", "enabled"}
_FALSY = {"false", "0", "no", "off", "n", "disabled"}
_LIST_SCALAR_KEYS = frozenset(
    {
        "connectionId",
        "search",
        "endUserId",
        "integrationId",
        "endUserOrganizationId",
        "limit",
        "page",
    }
)
_SINGLE_QUERY_KEYS = frozenset(
    {"provider_config_key", "refresh_token", "force_refresh", "refresh_github_app_jwt_token"}
)


def create_connections_router(
    list_connections: ListConnections,
    get_connection: GetConnection,
    crud_service: ConnectionCrudService,
) -> APIRouter:
    router = APIRouter(tags=["connections"])

    @router.get("/connections")
    async def list_connections_route(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        req = _parse_list_query(request, auth)
        items = await list_connections.execute(req)
        return JSONResponse(serialize_list(items))

    @router.get("/connections/{connection_id}")
    async def get_connection_route(
        connection_id: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _validate_connection_id(connection_id)
        provider_config_key, return_refresh_token = _parse_single_query(request)
        full = await get_connection.execute(
            GetConnectionRequest(
                context=auth,
                connection_id=connection_id,
                provider_config_key=provider_config_key,
                return_refresh_token=return_refresh_token,
            )
        )
        return JSONResponse(full_to_dict(full))

    @router.post("/connections")
    async def create_connection_route(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        import json as _json
        body = _json.loads(await request.body() or b"{}")
        result = await crud_service.create(
            CreateConnectionRequest(
                context=auth,
                provider_config_key=body.get("provider_config_key", ""),
                connection_id=body.get("connection_id"),
                credentials=body.get("credentials"),
                metadata=body.get("metadata"),
                connection_config=body.get("connection_config"),
                tags=body.get("tags"),
            )
        )
        return JSONResponse(result)

    @router.patch("/connections/{connection_id}")
    async def patch_connection_route(
        connection_id: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        provider_config_key: str = Query(..., alias="provider_config_key"),
    ) -> JSONResponse:
        import json as _json
        body = _json.loads(await request.body() or b"{}")
        await crud_service.patch(
            PatchConnectionRequest(
                context=auth,
                connection_id=connection_id,
                provider_config_key=provider_config_key,
                tags=body.get("tags"),
            )
        )
        return JSONResponse({"success": True})

    @router.delete("/connections/{connection_id}")
    async def delete_connection_route(
        connection_id: str,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        provider_config_key: str = Query(..., alias="provider_config_key"),
    ) -> JSONResponse:
        deleted = await crud_service.delete(
            DeleteConnectionRequest(
                context=auth,
                connection_id=connection_id,
                provider_config_key=provider_config_key,
            )
        )
        return JSONResponse({"success": deleted})

    @router.post("/connections/metadata")
    async def set_metadata_route(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        import json as _json
        body = _json.loads(await request.body() or b"{}")
        conn_ids = body.get("connection_id", [])
        if isinstance(conn_ids, str):
            conn_ids = [conn_ids]
        updated = await crud_service.set_metadata(
            SetMetadataRequest(
                context=auth,
                connection_ids=conn_ids,
                provider_config_key=body.get("provider_config_key", ""),
                metadata=body.get("metadata", {}),
            )
        )
        return JSONResponse({"updated": updated})

    @router.patch("/connections/metadata")
    async def update_metadata_route(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        import json as _json
        body = _json.loads(await request.body() or b"{}")
        conn_ids = body.get("connection_id", [])
        if isinstance(conn_ids, str):
            conn_ids = [conn_ids]
        updated = await crud_service.update_metadata(
            SetMetadataRequest(
                context=auth,
                connection_ids=conn_ids,
                provider_config_key=body.get("provider_config_key", ""),
                metadata=body.get("metadata", {}),
            )
        )
        return JSONResponse({"updated": updated})

    # Deprecated /connection routes (same handlers, legacy paths)
    @router.get("/connection", deprecated=True, response_model=None)
    async def list_connections_legacy(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        return await list_connections_route(request, auth)

    @router.get("/connection/{connection_id}", deprecated=True, response_model=None)
    async def get_connection_legacy(
        connection_id: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        return await get_connection_route(connection_id, request, auth)

    @router.delete("/connection/{connection_id}", deprecated=True, response_model=None)
    async def delete_connection_legacy(
        connection_id: str,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        provider_config_key: str = Query(..., alias="provider_config_key"),
    ) -> JSONResponse:
        return await delete_connection_route(connection_id, auth, provider_config_key)

    @router.post("/connection", deprecated=True, response_model=None)
    async def create_connection_legacy(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        return await create_connection_route(request, auth)

    @router.post("/connection/metadata", deprecated=True, response_model=None)
    async def set_metadata_legacy(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        return await set_metadata_route(request, auth)

    @router.patch("/connection/metadata", deprecated=True, response_model=None)
    async def update_metadata_legacy(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        return await update_metadata_route(request, auth)

    @router.post("/connection/{connection_id}/metadata", deprecated=True, response_model=None)
    async def set_metadata_per_connection_legacy(
        connection_id: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        provider_config_key: str = Query(..., alias="provider_config_key"),
    ) -> JSONResponse:
        import json as _json
        body = _json.loads(await request.body() or b"{}")
        updated = await crud_service.set_metadata(
            SetMetadataRequest(
                context=auth,
                connection_ids=[connection_id],
                provider_config_key=provider_config_key,
                metadata=body.get("metadata", {}),
            )
        )
        return JSONResponse({"updated": updated})

    @router.patch("/connection/{connection_id}/metadata", deprecated=True, response_model=None)
    async def update_metadata_per_connection_legacy(
        connection_id: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        provider_config_key: str = Query(..., alias="provider_config_key"),
    ) -> JSONResponse:
        import json as _json
        body = _json.loads(await request.body() or b"{}")
        updated = await crud_service.update_metadata(
            SetMetadataRequest(
                context=auth,
                connection_ids=[connection_id],
                provider_config_key=provider_config_key,
                metadata=body.get("metadata", {}),
            )
        )
        return JSONResponse({"updated": updated})

    return router


def _validate_connection_id(connection_id: str) -> None:
    if (
        len(connection_id) > _CONNECTION_ID_MAX
        or _CONNECTION_ID_RE.fullmatch(connection_id) is None
    ):
        raise ValidationApiError(
            "invalid_uri_params",
            [
                {
                    "code": "invalid_string",
                    "message": "Invalid input: connectionId must match the allowed charset",
                    "path": ["connectionId"],
                }
            ],
        )


def _parse_single_query(request: Request) -> tuple[str, bool]:
    provider_config_key: str | None = None
    refresh_token = False
    for key, value in request.query_params.multi_items():
        if key not in _SINGLE_QUERY_KEYS:
            raise _unrecognized(key)
        if key == "provider_config_key":
            provider_config_key = value
        elif key == "refresh_token":
            refresh_token = _stringbool(value, key)
        else:
            _stringbool(value, key)  # validate format, ignore result (refresh deferred)

    if provider_config_key is None:
        raise ValidationApiError(
            "invalid_query_params",
            [
                {
                    "code": "invalid_type",
                    "message": "provider_config_key is required",
                    "path": ["provider_config_key"],
                }
            ],
        )
    if (
        len(provider_config_key) > _CONNECTION_ID_MAX
        or _PROVIDER_CONFIG_KEY_RE.fullmatch(provider_config_key) is None
    ):
        raise ValidationApiError(
            "invalid_query_params",
            [
                {
                    "code": "invalid_string",
                    "message": "Invalid input: must match /^[a-zA-Z0-9~:.@ _-]+$/",
                    "path": ["provider_config_key"],
                }
            ],
        )
    return provider_config_key, refresh_token


def _parse_list_query(request: Request, auth: AuthenticatedContext) -> ListConnectionsRequest:
    scalars: dict[str, str] = {}
    tags: dict[str, str] = {}
    for key, value in request.query_params.multi_items():
        if key.startswith("tags[") and key.endswith("]"):
            tag_key = key[len("tags[") : -1]
            _validate_tag_key(tag_key, key)
            _validate_tag_value(value, key)
            tags[tag_key.lower()] = value
        elif key in _LIST_SCALAR_KEYS:
            scalars[key] = value
        else:
            raise _unrecognized(key)

    if len(tags) > _TAG_MAX_COUNT:
        raise ValidationApiError(
            "invalid_query_params",
            [
                {
                    "code": "custom",
                    "message": f"Tags cannot contain more than {_TAG_MAX_COUNT} keys",
                    "path": ["tags"],
                }
            ],
        )

    limit = _coerce_int(
        scalars.get("limit"), "limit", 1, _LIST_LIMIT_MAX, default=_LIST_LIMIT_DEFAULT
    )
    page = _coerce_int(scalars.get("page"), "page", 0, default=0)

    integration_ids: tuple[str, ...] = ()
    if "integrationId" in scalars:
        integration_ids = tuple(
            part.strip() for part in scalars["integrationId"].split(",") if part.strip()
        )

    return ListConnectionsRequest(
        context=auth,
        connection_id=_optional_scalar(scalars.get("connectionId"), "connectionId"),
        integration_ids=integration_ids,
        search=_optional_scalar(scalars.get("search"), "search"),
        end_user_id=_optional_scalar(scalars.get("endUserId"), "endUserId"),
        end_user_organization_id=_optional_scalar(
            scalars.get("endUserOrganizationId"), "endUserOrganizationId"
        ),
        tags=tags or None,
        limit=limit,
        page=page,
    )


def _optional_scalar(value: str | None, key: str) -> str | None:
    if value is None:
        return None
    if not value:
        raise ValidationApiError(
            "invalid_query_params",
            [
                {
                    "code": "too_small",
                    "message": f"{key} must be at least 1 character",
                    "path": [key],
                }
            ],
        )
    if len(value) > _CONNECTION_ID_MAX:
        raise ValidationApiError(
            "invalid_query_params",
            [
                {
                    "code": "too_big",
                    "message": f"{key} must be at most {_CONNECTION_ID_MAX} characters",
                    "path": [key],
                }
            ],
        )
    return value


def _validate_tag_key(tag_key: str, raw_key: str) -> None:
    if len(tag_key) > _TAG_KEY_MAX or _TAG_KEY_RE.fullmatch(tag_key) is None:
        raise ValidationApiError(
            "invalid_query_params",
            [
                {
                    "code": "invalid_string",
                    "message": (
                        "Tag keys must start with a letter and contain only alphanumerics,"
                        " underscores, hyphens, periods, or slashes"
                    ),
                    "path": ["tags", raw_key],
                }
            ],
        )


def _validate_tag_value(value: str, raw_key: str) -> None:
    if not value or len(value) > _TAG_VALUE_MAX:
        raise ValidationApiError(
            "invalid_query_params",
            [
                {
                    "code": "invalid_string",
                    "message": f"Tag values must be at most {_TAG_VALUE_MAX} characters",
                    "path": ["tags", raw_key],
                }
            ],
        )


def _coerce_int(
    raw: str | None,
    key: str,
    minimum: int,
    maximum: int | None = None,
    *,
    default: int,
) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValidationApiError(
            "invalid_query_params",
            [{"code": "invalid_type", "message": f"{key} must be a number", "path": [key]}],
        ) from None
    if value < minimum:
        raise ValidationApiError(
            "invalid_query_params",
            [{"code": "too_small", "message": f"{key} must be at least {minimum}", "path": [key]}],
        )
    if maximum is not None and value > maximum:
        raise ValidationApiError(
            "invalid_query_params",
            [{"code": "too_big", "message": f"{key} must be at most {maximum}", "path": [key]}],
        )
    return value


def _stringbool(value: str, key: str) -> bool:
    lowered = value.lower()
    if lowered in _TRUTHY:
        return True
    if lowered in _FALSY:
        return False
    raise ValidationApiError(
        "invalid_query_params",
        [{"code": "invalid_string", "message": f"{key} must be a boolean string", "path": [key]}],
    )


def _unrecognized(key: str) -> ValidationApiError:
    return ValidationApiError(
        "invalid_query_params",
        [
            {
                "code": "unrecognized_keys",
                "message": f"Unrecognized key '{key}' in query",
                "path": [],
            }
        ],
    )


__all__: list[Any] = []