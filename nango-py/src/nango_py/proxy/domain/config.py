"""Proxy configuration model.

A slim view of ``ApplicationConstructedProxyConfiguration`` carrying only what
the URL/header builders and the HTTP client need. The full provider entry
(``proxy.base_url``, ``proxy.headers``, ``proxy.query``, ``proxy.retry``) is
passed through as an opaque dict so new provider features don't require a
model change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ProxyConfig:
    endpoint: str
    method: str
    provider_entry: JsonObject  # full providers.yaml entry (proxy, auth_mode, ...)
    provider_name: str
    provider_config_key: str
    headers: JsonObject  # forwarded Nango-Proxy-* headers (lowercased keys)
    data: Any = None
    retries: int = 0
    base_url_override: str | None = None
    decompress: bool = False
    params: JsonObject | None = None
    retry_on: tuple[int, ...] = ()
    forward_headers_on_redirect: bool = True

    @property
    def proxy(self) -> JsonObject:
        return self.provider_entry.get("proxy") or {}

    @property
    def auth_mode(self) -> str:
        return str(self.provider_entry.get("auth_mode") or "")

    @property
    def require_client_certificate(self) -> bool:
        return bool(self.provider_entry.get("require_client_certificate"))