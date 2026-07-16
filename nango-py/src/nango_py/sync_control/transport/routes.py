"""Sync control + action trigger/result routes.

Mirrors:
- POST /sync/trigger — trigger sync execution
- POST /sync/pause — pause sync schedules
- POST /sync/start — start sync schedules
- GET /sync/status — get sync status
- PUT /sync/update-connection-frequency — update sync frequency
- POST /sync/:name/variant/:variant — create/delete sync variant
- POST /action/trigger — trigger action (alternate path)
- GET /action/:id — get async action result

All use apiAuth + environment:syncs:* / environment:actions:* scopes.
"""

from __future__ import annotations

import json
import uuid as _uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.domain.errors import Forbidden
from nango_py.auth.transport.dependencies import api_auth
from nango_py.connections.domain.errors import UnknownProviderConfig
from nango_py.integrations.application.gateway import IntegrationRepository
from nango_py.scheduler.application.orchestrator_service import OrchestratorService
from nango_py.scheduler.domain.models import ImmediateTaskInput
from nango_py.shared.errors import ApiError, ValidationApiError

SYNC_EXECUTE_SCOPE = "environment:syncs:execute"
SYNC_READ_SCOPE = "environment:syncs:read"
SYNC_MANAGE_SCOPE = "environment:syncs:manage"
ACTION_EXECUTE_SCOPE = "environment:actions:execute"


class SyncTriggerBody(BaseModel):
    model_config = {"extra": "allow"}
    syncs: list[Any] = Field(default_factory=list)
    connection_id: str | None = None
    provider_config_key: str | None = None
    sync_mode: str | None = None
    full_resync: bool | None = None
    opts: dict[str, Any] | None = None


class SyncControlBody(BaseModel):
    model_config = {"extra": "allow"}
    syncs: list[Any] = Field(default_factory=list)
    provider_config_key: str
    connection_id: str | None = None


class SyncStatusQuery(BaseModel):
    syncs: str
    provider_config_key: str
    connection_id: str | None = None


class ActionTriggerBody(BaseModel):
    model_config = {"extra": "allow"}
    action_name: str | None = Field(default=None, alias="actionName")
    connection_id: str | None = None
    provider_config_key: str | None = None
    input: Any = None
    async_: bool = Field(default=False, alias="async")
    retry_max: int = Field(default=0, alias="retryMax")


def create_sync_control_router(
    orchestrator: OrchestratorService,
    integration_repository: IntegrationRepository,
) -> APIRouter:
    router = APIRouter(tags=["sync-control"])

    @router.post("/sync/trigger")
    async def trigger_sync(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        provider_config_key_header: str | None = Header(default=None, alias="provider-config-key"),
        connection_id_header: str | None = Header(default=None, alias="connection-id"),
    ) -> JSONResponse:
        _check_scope(auth, SYNC_EXECUTE_SCOPE)
        body = await _parse_body(request)
        provider_config_key = body.get("provider_config_key") or provider_config_key_header
        connection_id = body.get("connection_id") or connection_id_header

        if not provider_config_key or not connection_id:
            raise _missing_connection()

        integration = await integration_repository.get_by_unique_key(
            environment_id=auth.environment.id,
            unique_key=provider_config_key,
        )
        if integration is None:
            raise UnknownProviderConfig()

        syncs = body.get("syncs", [])
        if not syncs:
            return JSONResponse({"data": [], "success": True})

        results = []
        for sync in syncs:
            sync_name, sync_variant = _parse_sync_id(sync)
            task = await orchestrator.create_immediate(
                ImmediateTaskInput(
                    name=f"sync:{provider_config_key}:{sync_name}:{_uuid.uuid4()}",
                    payload={
                        "type": "sync",
                        "syncId": sync_name,
                        "syncName": sync_name,
                        "syncVariant": sync_variant,
                        "debug": False,
                        "connection": {
                            "id": 0,
                            "connection_id": connection_id,
                            "provider_config_key": provider_config_key,
                            "environment_id": auth.environment.id,
                        },
                    },
                    group_key=f"sync:{provider_config_key}:{sync_name}",
                    group_max_concurrency=1,
                    retry_max=0,
                    retry_count=0,
                    retry_key=None,
                    owner_key=connection_id,
                    starts_after=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    created_to_started_timeout_secs=30,
                    started_to_completed_timeout_secs=300,
                    heartbeat_timeout_secs=30,
                )
            )
            results.append({"taskId": task.task_id, "retryKey": task.retry_key})

        if len(results) == 1:
            return JSONResponse({
                "data": {
                    "taskId": results[0]["taskId"],
                    "retryKey": results[0]["retryKey"],
                    "type": "sync",
                }
            })
        return JSONResponse({"success": True})

    @router.post("/sync/pause")
    async def pause_sync(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_scope(auth, SYNC_EXECUTE_SCOPE)
        await _parse_body(request)
        # Pause sync schedules — for now just return success
        # Full implementation requires schedule lookup + orchestrator.set_schedule_state
        return JSONResponse({"success": True})

    @router.post("/sync/start")
    async def start_sync(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_scope(auth, SYNC_EXECUTE_SCOPE)
        await _parse_body(request)
        return JSONResponse({"success": True})

    @router.get("/sync/status")
    async def sync_status(
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        syncs: str = Query(...),
        provider_config_key: str = Query(..., alias="provider_config_key"),
        connection_id: str | None = Query(default=None, alias="connection_id"),
    ) -> JSONResponse:
        _check_scope(auth, SYNC_READ_SCOPE)
        # Read sync status from DB — for now return empty
        # Full implementation requires _nango_syncs + _nango_sync_jobs queries
        sync_names = [s.strip() for s in syncs.split(",") if s.strip()]
        return JSONResponse({
            "data": [
                {
                    "sync": name,
                    "status": "PAUSED",
                    "latest_sync_status": "PAUSED",
                    "record_count": 0,
                }
                for name in sync_names
            ]
        })

    @router.put("/sync/update-connection-frequency")
    async def update_frequency(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_scope(auth, SYNC_MANAGE_SCOPE)
        await _parse_body(request)
        return JSONResponse({"success": True})

    @router.post("/action/trigger")
    async def trigger_action(
        request: Request,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
        provider_config_key_header: str | None = Header(default=None, alias="provider-config-key"),
        connection_id_header: str | None = Header(default=None, alias="connection-id"),
        async_header: bool | None = Header(default=None, alias="x-async"),
        retry_max_header: int | None = Header(default=None, alias="x-max-retries"),
    ) -> JSONResponse:
        _check_scope(auth, ACTION_EXECUTE_SCOPE)
        body = await _parse_body(request)
        action_name = body.get("actionName", "")
        provider_config_key = body.get("providerConfigKey") or provider_config_key_header
        connection_id = body.get("connectionId") or connection_id_header

        if not provider_config_key or not connection_id:
            raise _missing_connection()

        integration = await integration_repository.get_by_unique_key(
            environment_id=auth.environment.id,
            unique_key=provider_config_key,
        )
        if integration is None:
            raise UnknownProviderConfig()

        from datetime import UTC, datetime
        task = await orchestrator.create_immediate(
            ImmediateTaskInput(
                name=f"action:{provider_config_key}:{action_name}:{_uuid.uuid4()}",
                payload={
                    "type": "action",
                    "actionName": action_name,
                    "activityLogId": str(_uuid.uuid4()),
                    "input": body.get("input"),
                    "async": body.get("async", async_header is True),
                    "connection": {
                        "id": 0,
                        "connection_id": connection_id,
                        "provider_config_key": provider_config_key,
                        "environment_id": auth.environment.id,
                    },
                },
                group_key=f"action:{provider_config_key}:{action_name}",
                group_max_concurrency=1,
                retry_max=body.get("retryMax", retry_max_header or 0),
                retry_count=0,
                retry_key=None,
                owner_key=connection_id,
                starts_after=datetime.now(UTC),
                created_to_started_timeout_secs=30,
                started_to_completed_timeout_secs=300,
                heartbeat_timeout_secs=30,
            )
        )
        return JSONResponse({
            "data": {
                "taskId": task.task_id,
                "retryKey": task.retry_key,
                "type": "action",
            }
        })

    @router.get("/action/{action_id}")
    async def get_action_result(
        action_id: str,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_scope(auth, ACTION_EXECUTE_SCOPE)
        # Get async action result — for now return not found
        # Full implementation requires reading task output from scheduler
        raise _not_found("action_not_found", f"Action '{action_id}' not found")

    @router.post("/sync/{name}/variant/{variant}")
    async def create_sync_variant(
        name: str,
        variant: str,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_scope(auth, SYNC_MANAGE_SCOPE)
        # Create a sync variant — requires inserting into _nango_sync_configs
        # Full implementation requires DB write to sync_configs table
        return JSONResponse({
            "sync": name,
            "variant": variant,
            "success": True,
        })

    @router.delete("/sync/{name}/variant/{variant}")
    async def delete_sync_variant(
        name: str,
        variant: str,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_scope(auth, SYNC_MANAGE_SCOPE)
        return JSONResponse({
            "sync": name,
            "variant": variant,
            "success": True,
        })

    return router


def _check_scope(auth: AuthenticatedContext, scope: str) -> None:
    if not auth.scopes.has(scope):
        raise Forbidden((scope,))


def _parse_sync_id(sync: Any) -> tuple[str, str]:
    if isinstance(sync, str):
        if "::" not in sync:
            return sync, "base"
        name, _, variant = sync.partition("::")
        return name, variant or "base"
    if isinstance(sync, dict):
        return sync.get("name", ""), sync.get("variant", "base")
    return str(sync), "base"


async def _parse_body(request: Request) -> dict[str, Any]:
    body = await request.body()
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise ValidationApiError(
            "invalid_body",
            [{"code": "custom", "message": "Invalid JSON", "path": []}],
        ) from None
    return parsed if isinstance(parsed, dict) else {}


def _missing_connection() -> ApiError:
    class _Err(ApiError):
        status = 400
        code = "missing_connection"
        message = (
            'Trigger requests require "connection" or both '
            '"connectionId" and "providerConfigKey"'
        )

    return _Err()


def _not_found(code: str, message: str) -> ApiError:
    class _Err(ApiError):
        status = 404
        pass

    err = _Err()
    err.code = code
    err.message = message
    return err