"""FastAPI router for auth flow endpoints.

POST /api-auth/api-key/:providerConfigKey — store API key credentials
POST /api-auth/basic/:providerConfigKey — store basic auth credentials
POST /auth/unauthenticated/:providerConfigKey — create connection with no creds
GET  /oauth/connect/:providerConfigKey — build OAuth2 auth URL and redirect
GET  /oauth/callback/:providerConfigKey — exchange code for tokens, store connection

Authoritative behavior:
``packages/server/lib/controllers/auth/postApiKey.ts``,
``postBasic.ts``, ``postUnauthenticated.ts``,
``packages/server/lib/controllers/oauth.controller.ts``.

Deferred: credential testing, connect-session auth, HMAC, connection validation
hooks, OAuth2 per-provider custom clients, token exchange for non-standard
providers. Phase 5c covers the common path with ``api_auth`` (Bearer token).

Additional auth flow routes (oauth2/cc, oauth-outbound, app-store, tba,
two-step, jwt, bill, signature) follow the same create-connection pattern
with different credential types and expected_auth_mode values.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.transport.dependencies import api_auth
from nango_py.auth_flows.application.create_auth_connection import (
    CreateAuthConnection,
    CreateAuthConnectionRequest,
)
from nango_py.auth_flows.domain.errors import InvalidAuthMode, UnknownProviderTemplate
from nango_py.auth_flows.domain.oauth2 import (
    build_oauth2_connect_url,
    decode_state,
)
from nango_py.connections.application.gateway import ConnectionRepository
from nango_py.connections.domain.errors import UnknownProviderConfig
from nango_py.integrations.application.gateway import (
    IntegrationRepository,
    ProviderCatalog,
)
from nango_py.shared.errors import ValidationApiError


def create_auth_flows_router(
    create_auth_connection: CreateAuthConnection,
    integration_repository: IntegrationRepository,
    provider_catalog: ProviderCatalog,
    connection_repository: ConnectionRepository,
    *,
    callback_url_base: str = "http://localhost:3003",
) -> APIRouter:
    router = APIRouter(tags=["auth-flows"])
    base = callback_url_base.rstrip("/")

    @router.post("/api-auth/api-key/{provider_config_key}")
    async def api_key_auth_route(
        provider_config_key: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str | None = Query(default=None, alias="connection_id"),
    ) -> JSONResponse:
        body = await _json_body(request)
        api_key = body.get("apiKey")
        if not isinstance(api_key, str) or not api_key:
            raise _invalid_body("apiKey is required")
        result = await create_auth_connection.execute(
            CreateAuthConnectionRequest(
                context=auth,
                provider_config_key=provider_config_key,
                connection_id=connection_id,
                credentials={"type": "API_KEY", "apiKey": api_key},
                expected_auth_mode="API_KEY",
            )
        )
        return JSONResponse(
            {"connectionId": result.connection_id, "providerConfigKey": result.provider_config_key}
        )

    @router.post("/api-auth/basic/{provider_config_key}")
    async def basic_auth_route(
        provider_config_key: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str | None = Query(default=None, alias="connection_id"),
    ) -> JSONResponse:
        body = await _json_body(request)
        username = body.get("username")
        password = body.get("password")
        if not isinstance(username, str) or not username:
            raise _invalid_body("username is required")
        if not isinstance(password, str):
            raise _invalid_body("password is required")
        result = await create_auth_connection.execute(
            CreateAuthConnectionRequest(
                context=auth,
                provider_config_key=provider_config_key,
                connection_id=connection_id,
                credentials={
                    "type": "BASIC",
                    "username": username,
                    "password": password,
                },
                expected_auth_mode="BASIC",
            )
        )
        return JSONResponse(
            {"connectionId": result.connection_id, "providerConfigKey": result.provider_config_key}
        )

    @router.post("/auth/unauthenticated/{provider_config_key}")
    async def unauthenticated_auth_route(
        provider_config_key: str,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str | None = Query(default=None, alias="connection_id"),
    ) -> JSONResponse:
        result = await create_auth_connection.execute(
            CreateAuthConnectionRequest(
                context=auth,
                provider_config_key=provider_config_key,
                connection_id=connection_id,
                credentials={"type": "NONE"},
                expected_auth_mode="NONE",
            )
        )
        return JSONResponse(
            {"connectionId": result.connection_id, "providerConfigKey": result.provider_config_key}
        )

    @router.post("/oauth2/auth/{provider_config_key}")
    async def oauth2_cc_auth_route(
        provider_config_key: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str | None = Query(default=None, alias="connection_id"),
    ) -> JSONResponse:
        body = await _json_body(request)
        result = await create_auth_connection.execute(
            CreateAuthConnectionRequest(
                context=auth,
                provider_config_key=provider_config_key,
                connection_id=connection_id,
                credentials={
                    "type": "OAUTH2_CC",
                    **body,
                },
                expected_auth_mode="OAUTH2_CC",
            )
        )
        return JSONResponse(
            {"connectionId": result.connection_id, "providerConfigKey": result.provider_config_key}
        )

    @router.post("/auth/oauth-outbound/{provider_config_key}")
    async def oauth_outbound_auth_route(
        provider_config_key: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str | None = Query(default=None, alias="connection_id"),
    ) -> JSONResponse:
        body = await _json_body(request)
        result = await create_auth_connection.execute(
            CreateAuthConnectionRequest(
                context=auth,
                provider_config_key=provider_config_key,
                connection_id=connection_id,
                credentials={
                    "type": "OAUTH2",
                    **body,
                },
                expected_auth_mode="OAUTH2",
            )
        )
        return JSONResponse(
            {"connectionId": result.connection_id, "providerConfigKey": result.provider_config_key}
        )

    @router.post("/app-store-auth/{provider_config_key}")
    async def app_store_auth_route(
        provider_config_key: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str | None = Query(default=None, alias="connection_id"),
    ) -> JSONResponse:
        body = await _json_body(request)
        result = await create_auth_connection.execute(
            CreateAuthConnectionRequest(
                context=auth,
                provider_config_key=provider_config_key,
                connection_id=connection_id,
                credentials={
                    "type": "APP_STORE",
                    **body,
                },
                expected_auth_mode="APP_STORE",
            )
        )
        return JSONResponse(
            {"connectionId": result.connection_id, "providerConfigKey": result.provider_config_key}
        )

    @router.post("/auth/tba/{provider_config_key}")
    async def tba_auth_route(
        provider_config_key: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str | None = Query(default=None, alias="connection_id"),
    ) -> JSONResponse:
        body = await _json_body(request)
        result = await create_auth_connection.execute(
            CreateAuthConnectionRequest(
                context=auth,
                provider_config_key=provider_config_key,
                connection_id=connection_id,
                credentials={
                    "type": "TBA",
                    **body,
                },
                expected_auth_mode="TBA",
            )
        )
        return JSONResponse(
            {"connectionId": result.connection_id, "providerConfigKey": result.provider_config_key}
        )

    @router.post("/auth/two-step/{provider_config_key}")
    async def two_step_auth_route(
        provider_config_key: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str | None = Query(default=None, alias="connection_id"),
    ) -> JSONResponse:
        body = await _json_body(request)
        result = await create_auth_connection.execute(
            CreateAuthConnectionRequest(
                context=auth,
                provider_config_key=provider_config_key,
                connection_id=connection_id,
                credentials={
                    "type": "TWO_STEP",
                    **body,
                },
                expected_auth_mode="TWO_STEP",
            )
        )
        return JSONResponse(
            {"connectionId": result.connection_id, "providerConfigKey": result.provider_config_key}
        )

    @router.post("/auth/jwt/{provider_config_key}")
    async def jwt_auth_route(
        provider_config_key: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str | None = Query(default=None, alias="connection_id"),
    ) -> JSONResponse:
        body = await _json_body(request)
        result = await create_auth_connection.execute(
            CreateAuthConnectionRequest(
                context=auth,
                provider_config_key=provider_config_key,
                connection_id=connection_id,
                credentials={
                    "type": "JWT",
                    **body,
                },
                expected_auth_mode="JWT",
            )
        )
        return JSONResponse(
            {"connectionId": result.connection_id, "providerConfigKey": result.provider_config_key}
        )

    @router.post("/auth/bill/{provider_config_key}")
    async def bill_auth_route(
        provider_config_key: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str | None = Query(default=None, alias="connection_id"),
    ) -> JSONResponse:
        body = await _json_body(request)
        result = await create_auth_connection.execute(
            CreateAuthConnectionRequest(
                context=auth,
                provider_config_key=provider_config_key,
                connection_id=connection_id,
                credentials={
                    "type": "BILL",
                    **body,
                },
                expected_auth_mode="BILL",
            )
        )
        return JSONResponse(
            {"connectionId": result.connection_id, "providerConfigKey": result.provider_config_key}
        )

    @router.post("/auth/signature/{provider_config_key}")
    async def signature_auth_route(
        provider_config_key: str,
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str | None = Query(default=None, alias="connection_id"),
    ) -> JSONResponse:
        body = await _json_body(request)
        result = await create_auth_connection.execute(
            CreateAuthConnectionRequest(
                context=auth,
                provider_config_key=provider_config_key,
                connection_id=connection_id,
                credentials={
                    "type": "SIGNATURE",
                    **body,
                },
                expected_auth_mode="SIGNATURE",
            )
        )
        return JSONResponse(
            {"connectionId": result.connection_id, "providerConfigKey": result.provider_config_key}
        )

    @router.get("/oauth/connect/{provider_config_key}")
    async def oauth_connect_route(
        provider_config_key: str,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        connection_id: str | None = Query(default=None, alias="connection_id"),
    ) -> RedirectResponse:
        integration = await integration_repository.get_by_unique_key(
            environment_id=auth.environment.id,
            unique_key=provider_config_key,
        )
        if integration is None:
            raise UnknownProviderConfig()

        provider_entry = provider_catalog.entry(integration.provider)
        if provider_entry is None:
            raise UnknownProviderTemplate()

        auth_url = provider_entry.get("authorization_url")
        if not isinstance(auth_url, str):
            raise InvalidAuthMode("Provider has no authorization_url")

        redirect_uri = f"{base}/oauth/callback/{provider_config_key}"
        state = {
            "connectionId": connection_id or "",
            "providerConfigKey": provider_config_key,
            "environmentId": auth.environment.id,
        }

        url = build_oauth2_connect_url(
            authorization_url=auth_url,
            client_id=integration.oauth_client_id or "",
            redirect_uri=redirect_uri,
            scopes=_resolve_scopes(integration.oauth_scopes, provider_entry.get("default_scopes")),
            state=state,
        )
        return RedirectResponse(url=url, status_code=302)

    @router.get("/oauth/callback/{provider_config_key}")
    async def oauth_callback_route(
        provider_config_key: str,
        request: Request,
        code: str = Query(...),
        state: str = Query(...),
    ) -> JSONResponse:
        decoded_state = decode_state(state)
        connection_id = decoded_state.get("connectionId") or ""
        environment_id = int(decoded_state.get("environmentId") or 0)

        if not environment_id:
            raise _invalid_body("Invalid state: missing environmentId")

        integration = await integration_repository.get_by_unique_key(
            environment_id=environment_id,
            unique_key=provider_config_key,
        )
        if integration is None:
            raise UnknownProviderConfig()

        provider_entry = provider_catalog.entry(integration.provider)
        if provider_entry is None:
            raise UnknownProviderTemplate()

        token_url = provider_entry.get("token_url")
        if not isinstance(token_url, str):
            raise InvalidAuthMode("Provider has no token_url")

        redirect_uri = f"{base}/oauth/callback/{provider_config_key}"
        client_kwargs: dict[str, Any] = {"timeout": httpx.Timeout(30.0)}
        test_transport = getattr(request.app.state, "httpx_transport", None)
        if test_transport is not None:
            client_kwargs["transport"] = test_transport

        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": integration.oauth_client_id or "",
                    "client_secret": integration.oauth_client_secret or "",
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code != 200:
            raise InvalidAuthMode(f"Token exchange failed with status {response.status_code}")

        raw = response.json()
        credentials = {
            "type": "OAUTH2",
            "access_token": raw.get("access_token"),
            "refresh_token": raw.get("refresh_token"),
            "raw": raw,
        }
        if raw.get("expires_in"):
            from datetime import UTC, datetime, timedelta

            expires_at = datetime.now(UTC) + timedelta(seconds=int(raw["expires_in"]))
            credentials["expires_at"] = expires_at.isoformat()

        _, operation = await connection_repository.upsert_connection(
            environment_id=environment_id,
            config_id=integration.id or 0,
            connection_id=connection_id or str(__import__("uuid").uuid4()),
            provider_config_key=provider_config_key,
            credentials=credentials,
            connection_config={},
        )
        return JSONResponse(
            {"connectionId": connection_id, "providerConfigKey": provider_config_key}
        )

    return router


async def _json_body(request: Request) -> dict[str, Any]:
    body = await request.body()
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise _invalid_body("Invalid JSON body") from None
    return parsed if isinstance(parsed, dict) else {}


def _invalid_body(message: str) -> ValidationApiError:
    return ValidationApiError(
        "invalid_body",
        [{"code": "custom", "message": message, "path": []}],
    )


def _resolve_scopes(oauth_scopes: str | None, default_scopes: object) -> str | list[str] | None:
    if oauth_scopes:
        return oauth_scopes
    if isinstance(default_scopes, list):
        return default_scopes
    if isinstance(default_scopes, str):
        return default_scopes
    return None


__all__: list[Any] = []