"""FastAPI router for the integration-read boundary.

Owns transport concerns only: auth dependency, query/param validation, and
response serialization. Business policy lives in the use cases.

Authoritative behavior:
``packages/server/lib/controllers/integrations/uniqueKey/getIntegration.ts``,
``packages/server/lib/controllers/integrations/getListIntegrations.ts``,
``packages/server/lib/controllers/providers/getProviders.ts``,
``packages/server/lib/controllers/providers/getProvider.ts``.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.transport.connect_session_auth import connect_session_or_api_auth
from nango_py.auth.transport.dependencies import api_auth
from nango_py.integrations.application.crud import (
    CreateIntegrationRequest,
    DeleteIntegrationRequest,
    IntegrationCrudService,
    PatchIntegrationRequest,
)
from nango_py.integrations.application.get_integration import (
    GetIntegration,
    GetIntegrationRequest,
    IncludeKey,
)
from nango_py.integrations.application.list_integrations import (
    ListIntegrations,
    ListIntegrationsRequest,
)
from nango_py.integrations.domain.errors import ProviderNotFound
from nango_py.integrations.infrastructure.provider_catalog import YamlProviderCatalog
from nango_py.integrations.transport.serialize import serialize_view, view_to_dict
from nango_py.shared.errors import ValidationApiError

# providerConfigKeySchema in packages/server/lib/helpers/validation.ts.
_UNIQUE_KEY_RE = re.compile(r"^[a-zA-Z0-9~:.@ _-]+$")
_UNIQUE_KEY_MAX_LENGTH = 255
# providerNameSchema in packages/server/lib/helpers/validation.ts.
_PROVIDER_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_VALID_INCLUDE = frozenset({"webhook", "credentials"})


def create_integrations_router(
    get_integration: GetIntegration,
    list_integrations: ListIntegrations,
    crud_service: IntegrationCrudService,
    *,
    provider_catalog: YamlProviderCatalog,
    base_public_url: str,
) -> APIRouter:
    router = APIRouter(tags=["integrations"])
    base = base_public_url.rstrip("/")

    @router.get("/integrations")
    async def list_integrations_route(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(connect_session_or_api_auth)],
    ) -> JSONResponse:
        _require_empty_query(request)
        views = await list_integrations.execute(ListIntegrationsRequest(context=auth))
        return JSONResponse({"data": [view_to_dict(view) for view in views]})

    @router.get("/integrations/{unique_key}")
    async def get_integration_route(
        unique_key: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        include = _parse_include(request)
        _validate_unique_key(unique_key)
        view = await get_integration.execute(
            GetIntegrationRequest(unique_key=unique_key, include=include, context=auth)
        )
        return JSONResponse(serialize_view(view))

    @router.post("/integrations")
    async def create_integration_route(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        import json as _json
        body = _json.loads(await request.body() or b"{}")
        if not isinstance(body, dict):
            raise ValidationApiError(
            "invalid_body",
            [{"code": "custom", "message": "Invalid body", "path": []}],
        )
        result = await crud_service.execute_create(
            CreateIntegrationRequest(
                context=auth,
                provider=body.get("provider", ""),
                unique_key=body.get("unique_key", ""),
                display_name=body.get("display_name"),
                forward_webhooks=body.get("forward_webhooks", True),
                credentials=body.get("credentials"),
            )
        )
        return JSONResponse(serialize_view(result))

    @router.post("/integrations/quickstart")
    async def quickstart_integration_route(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        import json as _json
        body = _json.loads(await request.body() or b"{}")
        if not isinstance(body, dict):
            raise ValidationApiError(
            "invalid_body",
            [{"code": "custom", "message": "Invalid body", "path": []}],
        )
        result = await crud_service.execute_create(
            CreateIntegrationRequest(
                context=auth,
                provider=body.get("provider", ""),
                unique_key=body.get("unique_key", ""),
                display_name=body.get("display_name"),
                forward_webhooks=body.get("forward_webhooks", True),
            )
        )
        return JSONResponse(serialize_view(result))

    @router.patch("/integrations/{unique_key}")
    async def patch_integration_route(
        unique_key: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        import json as _json
        body = _json.loads(await request.body() or b"{}")
        if not isinstance(body, dict):
            raise ValidationApiError(
            "invalid_body",
            [{"code": "custom", "message": "Invalid body", "path": []}],
        )
        result = await crud_service.execute_patch(
            PatchIntegrationRequest(
                context=auth,
                unique_key=unique_key,
                new_unique_key=body.get("unique_key"),
                display_name=body.get("display_name"),
                forward_webhooks=body.get("forward_webhooks"),
                credentials=body.get("credentials"),
                custom=body.get("custom"),
            )
        )
        return JSONResponse(serialize_view(result))

    @router.delete("/integrations/{unique_key}")
    async def delete_integration_route(
        unique_key: str,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        await crud_service.execute_delete(
            DeleteIntegrationRequest(
                context=auth,
                unique_key=unique_key,
            )
        )
        return JSONResponse({"success": True})

    @router.get("/providers")
    async def list_providers_route(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(connect_session_or_api_auth)],
    ) -> JSONResponse:
        search = _parse_providers_search(request)
        data = _provider_list(provider_catalog, base, search)
        return JSONResponse({"data": data})

    @router.get("/providers/{provider}")
    async def get_provider_route(
        provider: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(connect_session_or_api_auth)],
    ) -> JSONResponse:
        _require_empty_query(request)
        _validate_provider_name(provider)
        entry = provider_catalog.entry(provider)
        if entry is None:
            raise ProviderNotFound(provider)
        return JSONResponse({"data": _provider_view(entry, provider, base)})

    return router


def _parse_include(request: Request) -> frozenset[IncludeKey]:
    values = [
        value
        for key, value in request.query_params.multi_items()
        if key == "include" and value
    ]
    invalid = [value for value in values if value not in _VALID_INCLUDE]
    if invalid:
        raise ValidationApiError(
            "invalid_query_params",
            [
                {
                    "code": "invalid_enum_value",
                    "message": (
                        f"Invalid input: expected 'webhook' | 'credentials',"
                        f" received '{invalid[0]}'"
                    ),
                    "path": ["include"],
                }
            ],
        )
    return cast("frozenset[IncludeKey]", frozenset(values))


def _validate_unique_key(unique_key: str) -> None:
    if (
        len(unique_key) > _UNIQUE_KEY_MAX_LENGTH
        or _UNIQUE_KEY_RE.fullmatch(unique_key) is None
    ):
        raise ValidationApiError(
            "invalid_uri_params",
            [
                {
                    "code": "invalid_string",
                    "message": "Invalid input: must match /^[a-zA-Z0-9~:.@ _-]+$/",
                    "path": ["uniqueKey"],
                }
            ],
        )


def _require_empty_query(request: Request) -> None:
    if request.query_params:
        raise ValidationApiError(
            "invalid_query_params",
            [
                {
                    "code": "unrecognized_keys",
                    "message": "Unrecognized key(s) in query",
                    "path": [],
                }
            ],
        )


def _validate_provider_name(provider: str) -> None:
    if len(provider) > _UNIQUE_KEY_MAX_LENGTH or _PROVIDER_NAME_RE.fullmatch(provider) is None:
        raise ValidationApiError(
            "invalid_uri_params",
            [
                {
                    "code": "invalid_string",
                    "message": "Invalid input: must match /^[a-zA-Z0-9_-]+$/",
                    "path": ["provider"],
                }
            ],
        )


def _parse_providers_search(request: Request) -> str | None:
    search_values = [
        value for key, value in request.query_params.multi_items() if key == "search"
    ]
    unknown = [key for key, _ in request.query_params.multi_items() if key != "search"]
    if unknown:
        raise ValidationApiError(
            "invalid_query_params",
            [
                {
                    "code": "unrecognized_keys",
                    "message": "Unrecognized key(s) in query",
                    "path": [],
                }
            ],
        )
    if not search_values:
        return None
    search = search_values[0]
    if _UNIQUE_KEY_RE.fullmatch(search) is None:
        raise ValidationApiError(
            "invalid_query_params",
            [
                {
                    "code": "invalid_string",
                    "message": "Invalid input: must match /^[a-zA-Z0-9~:.@ _-]+$/",
                    "path": ["search"],
                }
            ],
        )
    return search


def _provider_view(entry: dict[str, Any], name: str, base: str) -> dict[str, Any]:
    return {**entry, "name": name, "logo_url": f"{base}/images/template-logos/{name}.svg"}


def _provider_list(
    catalog: YamlProviderCatalog, base: str, search: str | None
) -> list[dict[str, Any]]:
    entries = catalog.entries()
    if search is None:
        return [
            _provider_view(entry, name, base)
            for name, entry in sorted(entries.items())
        ]
    try:
        pattern = re.compile(search, re.IGNORECASE)
    except re.error:
        return []
    return [
        _provider_view(entry, name, base)
        for name, entry in sorted(entries.items())
        if pattern.search(name)
    ]


__all__: list[Any] = []