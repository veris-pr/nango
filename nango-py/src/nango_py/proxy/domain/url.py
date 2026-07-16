"""Proxy URL construction.

Mirrors ``buildProxyURL`` in ``packages/shared/lib/services/proxy/utils.ts``:
base_url override OR provider.proxy.base_url (with ``connectionConfig`` fallback
``||``); strip trailing/leading slashes; interpolate connectionConfig and
credentials; apply params and provider.proxy.query.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode, urlunsplit

from nango_py.proxy.domain.config import ProxyConfig
from nango_py.proxy.domain.errors import ProxyError
from nango_py.proxy.domain.interpolate import interpolate

JsonObject = dict[str, Any]


def build_proxy_url(
    config: ProxyConfig,
    *,
    credentials: JsonObject,
    connection_config: JsonObject,
) -> str:
    api_base = config.base_url_override or config.proxy.get("base_url")
    if not api_base:
        raise ProxyError(
            "missing_api_url",
            "Missing API URL: provider has no proxy.base_url and no base-url-override",
        )

    api_base = _resolve_fallback(str(api_base), connection_config)

    normalized_base = str(api_base).rstrip("/")
    normalized_endpoint = config.endpoint.lstrip("/")

    combined = "/".join(part for part in (normalized_base, normalized_endpoint) if part)
    url_replacers = {
        "connectionConfig": connection_config,
        "credentials": credentials,
        **credentials,
    }
    full_endpoint = interpolate(combined, url_replacers)

    try:
        from urllib.parse import urlsplit as _urlsplit

        split = _urlsplit(full_endpoint)
    except ValueError as exc:
        raise ProxyError("unknown_error", f"Invalid proxy URL: {exc}") from exc

    query_pairs: list[tuple[str, str]] = []
    if split.query:
        query_pairs.extend(_parse_query(split.query))
    if config.params:
        for key, value in config.params.items():
            query_pairs.append((key, str(value)))
    query_pairs.extend(
        _provider_query(config, credentials=credentials, connection_config=connection_config)
    )

    new_query = urlencode(query_pairs, doseq=True)
    return urlunsplit((split.scheme, split.netloc, split.path, new_query, split.fragment))


def _resolve_fallback(api_base: str, connection_config: JsonObject) -> str:
    """Handle the ``${connectionConfig.x || default}`` base_url fallback."""
    if "||" not in api_base or "${" not in api_base:
        return api_base
    import re

    match = re.search(r"connectionConfig\.(\w+)", api_base)
    if match and match.group(1) and match.group(1) in connection_config:
        return api_base.split("||")[0].strip()
    return api_base.split("||", 1)[1].strip()


def _provider_query(
    config: ProxyConfig,
    *,
    credentials: JsonObject,
    connection_config: JsonObject,
) -> list[tuple[str, str]]:
    query = config.proxy.get("query") or {}
    if not isinstance(query, dict):
        return []
    pairs: list[tuple[str, str]] = []
    for key, value in query.items():
        if not isinstance(value, str):
            continue
        if credentials.get("type") == "API_KEY" and value == "${apiKey}":
            api_key = credentials.get("apiKey")
            if isinstance(api_key, str):
                pairs.append((key, api_key))
        elif value.startswith("connectionConfig."):
            field = value.removeprefix("connectionConfig.")
            if field in connection_config:
                pairs.append((key, str(connection_config[field])))
        elif "${" not in value:
            pairs.append((key, value))
    return pairs


def _parse_query(query: str) -> list[tuple[str, str]]:
    from urllib.parse import parse_qsl

    return parse_qsl(query, keep_blank_values=True)