"""OAuth2 connect URL builder and state encoding.

Mirrors the URL construction in
``packages/server/lib/controllers/oauth.controller.ts`` ``oauthRequest``.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import urlencode

JsonObject = dict[str, Any]


def build_oauth2_connect_url(
    *,
    authorization_url: str,
    client_id: str,
    redirect_uri: str,
    scopes: str | list[str] | None,
    state: JsonObject,
    connection_config: JsonObject | None = None,
    extra_params: JsonObject | None = None,
) -> str:
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
    }
    if scopes:
        scope_str = " ".join(scopes) if isinstance(scopes, list) else str(scopes)
        if scope_str:
            params["scope"] = scope_str
    if connection_config:
        for key, value in connection_config.items():
            if isinstance(value, str) and key not in params:
                params[key] = value
    if extra_params:
        for key, value in extra_params.items():
            if isinstance(value, str):
                params[key] = value
    params["state"] = encode_state(state)
    return f"{authorization_url}?{urlencode(params)}"


def encode_state(state: JsonObject) -> str:
    return base64.urlsafe_b64encode(json.dumps(state).encode()).decode()


def decode_state(encoded: str) -> JsonObject:
    decoded = base64.urlsafe_b64decode(encoded.encode()).decode()
    parsed = json.loads(decoded)
    if not isinstance(parsed, dict):
        raise ValueError("state must be a JSON object")
    return parsed