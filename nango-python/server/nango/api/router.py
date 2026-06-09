from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request

from nango.api.models import (
    ActionTriggerRequest,
    ConnectSessionResponse,
    DataEnvelope,
    DeployValidationRequest,
    DeployValidationResponse,
    IntegrationListResponse,
    IntegrationResponse,
    ProviderListResponse,
    ProviderResponse,
    PublicConnectionFull,
    PublicConnectionListResponse,
    PublicSyncTriggerRequest,
    SuccessResponse,
    SyncTriggerIdentifierInput,
    SyncTriggerRequest,
    TriggerTaskData,
    TriggerTaskResponse,
)
from nango.api.service import PublicAPIService
from nango.auth.dependencies import api_auth
from nango.auth.models import AccountContext
from nango.contracts.connect import ConnectSessionCreateRequest, ConnectSessionCreateResponse
from nango.utils.errors import ApplicationError


def create_public_api_router(service: PublicAPIService | None = None) -> APIRouter:
    api = service or PublicAPIService()
    router = APIRouter(tags=["public-api"])

    @router.get("/providers", response_model=ProviderListResponse)
    async def list_providers(
        accept_language: str | None = Header(default=None),
    ) -> ProviderListResponse:
        language = accept_language.split(",", 1)[0].strip() if accept_language else None
        return ProviderListResponse(data=api.list_providers(language=language or None))

    @router.get("/providers/{provider}", response_model=ProviderResponse)
    async def get_provider(provider: str) -> ProviderResponse:
        return ProviderResponse(data=api.get_provider(provider))

    @router.get("/integrations", response_model=IntegrationListResponse)
    async def list_integrations() -> IntegrationListResponse:
        return IntegrationListResponse(data=await api.list_integrations())

    @router.get("/integrations/{provider_config_key}", response_model=IntegrationResponse)
    async def get_integration(provider_config_key: str) -> IntegrationResponse:
        return IntegrationResponse(data=await api.get_integration(provider_config_key))

    @router.get(
        "/connection",
        response_model=PublicConnectionListResponse,
        response_model_exclude_none=True,
        deprecated=True,
    )
    @router.get(
        "/connections",
        response_model=PublicConnectionListResponse,
        response_model_exclude_none=True,
    )
    async def list_connections(
        request: Request,
        auth: Annotated[AccountContext, Depends(api_auth)],
        connection_id: str | None = Query(default=None, alias="connectionId"),
        integration_id: str | None = Query(default=None, alias="integrationId"),
        search: str | None = Query(default=None, min_length=1, max_length=255),
        end_user_id: str | None = Query(default=None, alias="endUserId"),
        end_user_organization_id: str | None = Query(
            default=None,
            alias="endUserOrganizationId",
        ),
        limit: int = Query(default=10_000, ge=1, le=10_000),
        page: int = Query(default=0, ge=0),
    ) -> PublicConnectionListResponse:
        return PublicConnectionListResponse(
            connections=await api.list_public_connections(
                auth=auth,
                connection_id=connection_id,
                integration_id=integration_id,
                search=search,
                end_user_id=end_user_id,
                end_user_organization_id=end_user_organization_id,
                tags=_query_tags(request),
                limit=limit,
                page=page,
            )
        )

    @router.get(
        "/connection/{connection_id}",
        response_model=PublicConnectionFull,
        response_model_exclude_none=True,
        deprecated=True,
    )
    @router.get(
        "/connections/{connection_id}",
        response_model=PublicConnectionFull,
        response_model_exclude_none=True,
    )
    async def get_connection(
        connection_id: str,
        provider_config_key: Annotated[str, Query(min_length=1)],
        auth: Annotated[AccountContext, Depends(api_auth)],
    ) -> PublicConnectionFull:
        return await api.get_public_connection(
            connection_id=connection_id,
            provider_config_key=provider_config_key,
            auth=auth,
        )

    @router.post("/connect/sessions", response_model=ConnectSessionCreateResponse)
    async def create_connect_session(
        request: ConnectSessionCreateRequest,
    ) -> ConnectSessionCreateResponse:
        return api.connect_sessions.create(request)

    @router.get(
        "/connect/session",
        response_model=ConnectSessionResponse,
        response_model_exclude_none=True,
    )
    async def get_connect_session(
        authorization: str | None = Header(default=None),
    ) -> ConnectSessionResponse:
        token = _bearer_token(authorization)
        session = api.connect_sessions.get(token)
        if session is None:
            raise ApplicationError(
                "connect_session_not_found",
                message="Connect session was not found or has expired",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return ConnectSessionResponse(data=session)

    @router.post("/sync/deploy", response_model=DeployValidationResponse)
    async def validate_deploy(request: DeployValidationRequest) -> DeployValidationResponse:
        return DeployValidationResponse(data=api.validate_deploy(request))

    @router.post("/sync/deploy/confirmation", response_model=DataEnvelope)
    async def deploy_confirmation_placeholder() -> DataEnvelope:
        return DataEnvelope(data={"requiresConfirmation": False, "placeholder": True})

    @router.post("/sync/deploy/internal", response_model=DataEnvelope)
    async def deploy_internal_placeholder() -> DataEnvelope:
        raise _not_implemented("sync_deploy_internal_not_implemented")

    @router.post("/sync/trigger", response_model=TriggerTaskResponse | SuccessResponse)
    async def trigger_sync(
        request: PublicSyncTriggerRequest,
        provider_config_key_header: Annotated[
            str | None, Header(alias="provider-config-key")
        ] = None,
        connection_id_header: Annotated[str | None, Header(alias="connection-id")] = None,
    ) -> TriggerTaskResponse | SuccessResponse:
        normalized_request = _normalize_sync_trigger_request(
            request,
            provider_config_key_header=provider_config_key_header,
            connection_id_header=connection_id_header,
        )
        if isinstance(normalized_request, list):
            await api.trigger_syncs(normalized_request)
            return SuccessResponse(success=True)
        task_id, retry_key = await api.trigger_sync(normalized_request)
        return TriggerTaskResponse(
            data=TriggerTaskData(taskId=task_id, retryKey=retry_key, type="sync")
        )

    @router.post("/action/trigger", response_model=TriggerTaskResponse)
    async def trigger_action(
        request: ActionTriggerRequest,
        provider_config_key_header: Annotated[
            str | None, Header(alias="provider-config-key")
        ] = None,
        connection_id_header: Annotated[str | None, Header(alias="connection-id")] = None,
        async_header: Annotated[bool | None, Header(alias="x-async")] = None,
        retry_max_header: Annotated[
            int | None, Header(alias="x-max-retries", ge=0, le=5)
        ] = None,
    ) -> TriggerTaskResponse:
        merged_request = ActionTriggerRequest.model_validate(
            {
                **request.model_dump(mode="python", by_alias=True, exclude_none=True),
                **(
                    {"providerConfigKey": provider_config_key_header}
                    if provider_config_key_header is not None
                    else {}
                ),
                **(
                    {"connectionId": connection_id_header}
                    if connection_id_header is not None
                    else {}
                ),
                **({"async": async_header} if async_header is not None else {}),
                **(
                    {"retryMax": retry_max_header}
                    if retry_max_header is not None
                    else {}
                ),
            }
        )
        task_id, retry_key = await api.trigger_action(merged_request)
        return TriggerTaskResponse(
            data=TriggerTaskData(taskId=task_id, retryKey=retry_key, type="action")
        )

    @router.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    async def future_route_groups_placeholder(request: Request) -> DataEnvelope:
        if request.url.path in {"/connect/telemetry"} or request.url.path.startswith(
            ("/plans", "/stripe", "/orb")
        ):
            raise ApplicationError(
                "route_not_found",
                message="Telemetry and billing routes are outside the Python API server scope",
                status_code=HTTPStatus.NOT_FOUND,
            )
        raise _not_implemented("route_group_not_implemented")

    return router


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApplicationError(
            "missing_connect_session_token",
            message="Connect session token must be passed as a bearer token",
            status_code=HTTPStatus.UNAUTHORIZED,
        )
    return authorization.split(" ", 1)[1].strip()


def _not_implemented(code: str) -> ApplicationError:
    return ApplicationError(
        code,
        message="This TypeScript route group has not been ported to Python yet",
        status_code=HTTPStatus.NOT_IMPLEMENTED,
    )


def _normalize_sync_trigger_request(
    request: PublicSyncTriggerRequest,
    *,
    provider_config_key_header: str | None,
    connection_id_header: str | None,
) -> SyncTriggerRequest | list[SyncTriggerRequest]:
    if request.syncs is None:
        return SyncTriggerRequest.model_validate(
            {
                **request.model_dump(mode="python", by_alias=True, exclude_none=True),
                **(
                    {"providerConfigKey": provider_config_key_header}
                    if provider_config_key_header is not None
                    else {}
                ),
                **(
                    {"connectionId": connection_id_header}
                    if connection_id_header is not None
                    else {}
                ),
            }
        )

    provider_config_key = request.provider_config_key or provider_config_key_header
    if not provider_config_key:
        raise ApplicationError(
            "missing_provider_config_key",
            message=(
                "Missing provider_config_key. Provide it in the body or headers."
            ),
            status_code=HTTPStatus.BAD_REQUEST,
        )

    connection_id = request.connection_id or connection_id_header
    if not connection_id:
        raise ApplicationError(
            "sync_trigger_not_implemented",
            message=(
                "Python sync trigger currently requires a single connection_id"
            ),
            status_code=HTTPStatus.NOT_IMPLEMENTED,
        )

    if request.opts and (request.opts.reset or request.opts.empty_cache):
        if request.sync_mode is not None or request.full_resync is not None:
            raise ApplicationError(
                "invalid_body",
                message=(
                    "Cannot use opts with deprecated sync_mode/full_resync parameters"
                ),
                status_code=HTTPStatus.BAD_REQUEST,
            )
        raise ApplicationError(
            "sync_trigger_not_implemented",
            message=(
                "Python sync trigger does not yet support reset or emptyCache options"
            ),
            status_code=HTTPStatus.NOT_IMPLEMENTED,
        )

    if request.sync_mode in {"full_refresh", "full_refresh_and_clear_cache"}:
        raise ApplicationError(
            "sync_trigger_not_implemented",
            message=(
                "Python sync trigger does not yet support full refresh modes"
            ),
            status_code=HTTPStatus.NOT_IMPLEMENTED,
        )

    if request.full_resync:
        raise ApplicationError(
            "sync_trigger_not_implemented",
            message=(
                "Python sync trigger does not yet support full_resync requests"
            ),
            status_code=HTTPStatus.NOT_IMPLEMENTED,
        )

    requests: list[SyncTriggerRequest] = []
    for sync in request.syncs:
        sync_name, sync_variant = _sync_identifier(sync)
        requests.append(
            SyncTriggerRequest(
                syncId=request.sync_id,
                syncName=sync_name,
                syncVariant=sync_variant,
                debug=request.debug,
                connection=request.connection,
                connectionId=connection_id,
                providerConfigKey=provider_config_key,
                environmentId=request.environment_id,
            )
        )
    if len(requests) == 1:
        return requests[0]
    return requests


def _sync_identifier(sync: str | SyncTriggerIdentifierInput) -> tuple[str, str]:
    if isinstance(sync, str):
        if "::" not in sync:
            return sync, "base"
        name, _, variant = sync.partition("::")
        return name, variant or "base"

    return sync.name, sync.variant


def _query_tags(request: Request) -> dict[str, str] | None:
    tags = {
        key.removeprefix("tags[").removesuffix("]"): value
        for key, value in request.query_params.multi_items()
        if key.startswith("tags[") and key.endswith("]") and value
    }
    return tags or None
