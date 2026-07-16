"""Webhook ingress route.

POST /webhook/{environment_uuid}/{provider_config_key} — receive external
provider webhooks and route them to sync triggers.

Auth: none (identified by environment UUID + provider config key in path).
Rate-limited in TS via webhookIngressRateLimit middleware.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from nango_py.shared.errors import ApiError


def create_webhook_router() -> APIRouter:
    router = APIRouter(tags=["webhook"])

    @router.post("/webhook/{environment_uuid}/{provider_config_key}")
    async def webhook_ingress(
        environment_uuid: str,
        provider_config_key: str,
        request: Request,
    ) -> JSONResponse:
        body_bytes = await request.body()
        try:
            json.loads(body_bytes) if body_bytes else {}
        except json.JSONDecodeError:
            raise _invalid_body("Invalid JSON body") from None

        # Resolve environment by UUID, find integration, route webhook
        # Full implementation requires:
        # 1. Look up environment by UUID
        # 2. Find integration by provider_config_key
        # 3. Verify webhook signature (provider-specific)
        # 4. Route to sync trigger or custom webhook handler
        # For now, acknowledge receipt
        return JSONResponse(
            {
                "success": True,
                "environment_uuid": environment_uuid,
                "provider_config_key": provider_config_key,
            }
        )

    return router


def _invalid_body(message: str) -> ApiError:
    class _Err(ApiError):
        status = 400
        code = "invalid_body"

    err = _Err()
    err.message = message
    return err