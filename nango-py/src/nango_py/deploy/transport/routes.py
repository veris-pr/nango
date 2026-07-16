"""Deploy routes: POST /sync/deploy, /sync/deploy/confirmation, /sync/deploy/internal.

Mirrors ``packages/server/lib/controllers/sync/deploy/``.

POST /sync/deploy — validate + parse nango.yaml, return metadata.
  Body: { nangoYamlBody: string, flowConfigs: [...], reconcile: bool, debug: bool }
  Auth: apiAuth + environment:deploy scope

POST /sync/deploy/confirmation — same validation, dry-run (no persistence).
  Same body + auth.

POST /sync/deploy/internal — internal deploy (same as deploy but different scope).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.domain.errors import Forbidden
from nango_py.auth.transport.dependencies import api_auth
from nango_py.deploy.application.validator import DeployValidator

DEPLOY_SCOPE = "environment:deploy"


class DeployBody(BaseModel):
    model_config = {"extra": "allow"}

    nango_yaml_body: str | None = Field(default=None, alias="nangoYamlBody")
    yaml: str | None = None
    flow_configs: list[dict[str, Any]] = Field(default_factory=list, alias="flowConfigs")
    reconcile: bool = False
    debug: bool = False


def create_deploy_router(validator: DeployValidator | None = None) -> APIRouter:
    router = APIRouter(tags=["deploy"])
    _validator = validator or DeployValidator()

    @router.post("/sync/deploy")
    async def deploy(
        body: DeployBody,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_scope(auth)
        yaml_text = body.nango_yaml_body or body.yaml
        result = _validator.validate(yaml_text)
        return JSONResponse({
            "data": {
                "valid": result.valid,
                "metadata": result.metadata,
                "errors": result.errors,
                "warnings": result.warnings,
            }
        })

    @router.post("/sync/deploy/confirmation")
    async def deploy_confirmation(
        body: DeployBody,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_scope(auth)
        yaml_text = body.nango_yaml_body or body.yaml
        result = _validator.validate(yaml_text)
        return JSONResponse({
            "data": {
                "requiresConfirmation": True,
                "valid": result.valid,
                "metadata": result.metadata,
            }
        })

    @router.post("/sync/deploy/internal")
    async def deploy_internal(
        body: DeployBody,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        _check_scope(auth)
        yaml_text = body.nango_yaml_body or body.yaml
        result = _validator.validate(yaml_text)
        return JSONResponse({
            "data": {
                "valid": result.valid,
                "metadata": result.metadata,
            }
        })

    return router


def _check_scope(auth: AuthenticatedContext) -> None:
    if not auth.scopes.has(DEPLOY_SCOPE):
        raise Forbidden((DEPLOY_SCOPE,))