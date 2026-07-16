"""Proxy retry decision.

Mirrors ``getProxyRetryFromErr`` in
``packages/shared/lib/services/proxy/retry.ts`` for the common cases:
network errors, default retryable statuses (>=500, 429, 401), the
``retry-on`` header, ``provider.proxy.retry.error_code`` (exact / ``Nxx`` /
``NNN-MMM``), and ``provider.proxy.retry.remaining`` header == '0'.

Deferred to Phase 4b: header/body-based backoff wait times (``retry.at`` /
``retry.after`` / ``retry.in_body``). Phase 4a uses exponential backoff instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nango_py.proxy.domain.config import ProxyConfig

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class RetryReason:
    retry: bool
    reason: str
    wait: float | None = None


# Mirror networkError in packages/utils/lib.
NETWORK_ERROR_CODES = frozenset(
    {"ECONNRESET", "ETIMEDOUT", "ECONNREFUSED", "EHOSTUNREACH", "ENETUNREACH", "EAI_AGAIN"}
)


def get_proxy_retry_from_err(
    *,
    is_network_error: bool = False,
    status: int | None = None,
    headers: JsonObject | None = None,
    proxy_config: ProxyConfig,
    retry_on: tuple[int, ...] = (),
) -> RetryReason:
    if is_network_error:
        return RetryReason(retry=True, reason="network_error")

    status_code = status or 0
    retry_conf = proxy_config.proxy.get("retry") or {}

    # provider.proxy.retry.error_code (explicit list) takes precedence.
    error_codes = retry_conf.get("error_code") if isinstance(retry_conf, dict) else None
    if isinstance(error_codes, list):
        for code in error_codes:
            if _matches_status(status_code, str(code)):
                return RetryReason(retry=True, reason=f"provider_error_code_{code}")
        if error_codes:
            # Explicit list provided but none matched → not retryable by default.
            pass
    else:
        if status_code >= 500 or status_code == 429 or status_code == 401:
            return RetryReason(retry=True, reason=f"status_code_{status_code}")

    if status_code in retry_on:
        return RetryReason(retry=True, reason=f"retry_on_{status_code}")

    remaining_header = retry_conf.get("remaining") if isinstance(retry_conf, dict) else None
    if isinstance(remaining_header, str) and headers:
        value = headers.get(remaining_header) or headers.get(remaining_header.lower())
        if isinstance(value, str) and value == "0":
            return RetryReason(retry=True, reason="provider_remaining")

    return RetryReason(retry=False, reason="not_retryable")


def _matches_status(status: int, rule: str) -> bool:
    if not rule:
        return False
    if rule.isdigit():
        return status == int(rule)
    xx = _XX_RE.fullmatch(rule)
    if xx:
        return status // 100 == int(xx.group(1))
    rng = _RANGE_RE.fullmatch(rule)
    if rng:
        return int(rng.group(1)) <= status <= int(rng.group(2))
    return False


import re  # noqa: E402

_XX_RE = re.compile(r"^(\d)xx$", re.IGNORECASE)
_RANGE_RE = re.compile(r"^(\d{3})-(\d{3})$")


def backoff_wait(
    attempt: int,
    *,
    base_ms: float = 500.0,
    factor: float = 2.0,
    max_ms: float = 30_000.0,
) -> float:
    """Exponential backoff in seconds for Phase 4a (replaces header-based waits)."""
    wait_ms = min(base_ms * (factor ** (attempt - 1)), max_ms)
    return wait_ms / 1000.0