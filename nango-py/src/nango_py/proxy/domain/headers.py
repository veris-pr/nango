"""Proxy header construction.

Mirrors ``buildProxyHeaders`` in ``packages/shared/lib/services/proxy/utils.ts``
for the common auth modes (OAUTH2, API_KEY, BASIC, APP, OAUTH2_CC, JWT,
SIGNATURE, TWO_STEP, CUSTOM, BILL, NONE) plus provider ``proxy.headers``
template interpolation.

Deferred to Phase 4b: TBA / OAUTH1 HMAC signing, the canonical-params /
endpoint / host / path / body base replacers (rare; used by a few providers like
Duo), and the ``user-agent`` provided-header override edge case.
"""

from __future__ import annotations

import base64
from typing import Any

from nango_py.proxy.domain.config import ProxyConfig
from nango_py.proxy.domain.interpolate import interpolate

JsonObject = dict[str, Any]


def build_proxy_headers(
    config: ProxyConfig,
    *,
    url: str,
    credentials: JsonObject,
    connection_config: JsonObject,
    integration_config: JsonObject | None = None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    creds_type = str(credentials.get("type") or "")

    auth = _default_authorization(creds_type, credentials, connection_config, integration_config)
    if auth is not None:
        headers["authorization"] = auth

    provider_headers = config.proxy.get("headers") or {}
    if isinstance(provider_headers, dict):
        for key, template in provider_headers.items():
            if not isinstance(template, str):
                continue
            headers[key] = _interpolate_provider_header(
                template,
                creds_type=creds_type,
                credentials=credentials,
                connection_config=connection_config,
                integration_config=integration_config or {},
            )

    # Forwarded Nango-Proxy-* headers override provider defaults (except user-agent).
    for key, value in config.headers.items():
        headers[key.lower()] = str(value)

    return headers


def _default_authorization(
    creds_type: str,
    credentials: JsonObject,
    connection_config: JsonObject,
    integration_config: JsonObject | None,
) -> str | None:
    if creds_type == "BASIC":
        username = str(credentials.get("username") or "")
        password = str(credentials.get("password") or "")
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        return f"Basic {token}"
    if creds_type in ("OAUTH2", "APP", "APP_STORE"):
        access_token: object = credentials.get("access_token")
        return f"Bearer {access_token}" if isinstance(access_token, str) else None
    if creds_type in ("OAUTH2_CC", "JWT", "SIGNATURE"):
        bearer_token: object = credentials.get("token")
        return f"Bearer {bearer_token}" if isinstance(bearer_token, str) else None
    if creds_type == "TWO_STEP":
        two_step_token: object = credentials.get("token")
        return f"Bearer {two_step_token}" if isinstance(two_step_token, str) else None
    # API_KEY, CUSTOM, BILL, NONE, undefined → no default Authorization.
    return None


def _interpolate_provider_header(
    template: str,
    *,
    creds_type: str,
    credentials: JsonObject,
    connection_config: JsonObject,
    integration_config: JsonObject,
) -> str:
    if "connectionConfig" in template:
        return interpolate(
            template,
            {
                "connectionConfig": connection_config,
                "credentials": credentials,
                **credentials,
                "method": None,
            },
        )
    if creds_type == "OAUTH2":
        return interpolate(
            template,
            {
                "accessToken": credentials.get("access_token", ""),
                "clientId": integration_config.get("oauth_client_id", ""),
                "clientSecret": integration_config.get("oauth_client_secret", ""),
            },
        )
    if creds_type in ("JWT", "OAUTH2_CC", "SIGNATURE", "TWO_STEP"):
        return interpolate(template, {"accessToken": credentials.get("token", "")})
    return interpolate(
        template,
        {"credentials": credentials, **credentials, "method": None},
    )