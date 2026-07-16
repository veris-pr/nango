"""Unit tests for proxy domain builders: interpolation, URL, headers, retry."""

from __future__ import annotations

from typing import Any

import pytest

from nango_py.proxy.domain.config import ProxyConfig
from nango_py.proxy.domain.errors import ProxyError
from nango_py.proxy.domain.headers import build_proxy_headers
from nango_py.proxy.domain.interpolate import interpolate
from nango_py.proxy.domain.retry import (
    backoff_wait,
    get_proxy_retry_from_err,
)
from nango_py.proxy.domain.url import build_proxy_url

# -- interpolate --


def test_interpolate_simple_placeholder() -> None:
    assert interpolate("Bearer ${accessToken}", {"accessToken": "tok-123"}) == "Bearer tok-123"


def test_interpolate_connection_config() -> None:
    result = interpolate(
        "https://${connectionConfig.domain}/api",
        {"connectionConfig": {"domain": "api.example.com"}},
    )
    assert result == "https://api.example.com/api"


def test_interpolate_unmatched_left_as_is() -> None:
    assert interpolate("${unknown}", {}) == "${unknown}"


def test_interpolate_no_placeholders() -> None:
    assert interpolate("https://api.example.com", {}) == "https://api.example.com"


# -- build_proxy_url --


def _oauth2_provider_entry() -> dict[str, object]:
    return {"auth_mode": "OAUTH2", "proxy": {"base_url": "https://api.github.com"}}


def _api_key_provider_entry() -> dict[str, object]:
    return {
        "auth_mode": "API_KEY",
        "proxy": {
            "base_url": "https://${connectionConfig.domain}/scim",
            "headers": {"authorization": "Bearer ${apiKey}"},
            "query": {"per_page": "100"},
        },
    }


def _config(
    endpoint: str = "/",
    provider_entry: dict[str, Any] | None = None,
    **kwargs: Any,
) -> ProxyConfig:
    headers = kwargs.pop("headers", {})
    return ProxyConfig(
        endpoint=endpoint,
        method="GET",
        provider_entry=provider_entry or _oauth2_provider_entry(),
        provider_name="github",
        provider_config_key="github",
        headers=headers,
        **kwargs,
    )


def test_build_url_base_plus_endpoint() -> None:
    url = build_proxy_url(
        _config(endpoint="/repos/octocat/hello"),
        credentials={"type": "OAUTH2", "access_token": "tok"},
        connection_config={},
    )
    assert url == "https://api.github.com/repos/octocat/hello"


def test_build_url_base_url_override() -> None:
    url = build_proxy_url(
        _config(endpoint="/users", base_url_override="https://api.github.enterprise.com"),
        credentials={"type": "OAUTH2", "access_token": "tok"},
        connection_config={},
    )
    assert url == "https://api.github.enterprise.com/users"


def test_build_url_connection_config_interpolation() -> None:
    url = build_proxy_url(
        _config(endpoint="/Users", provider_entry=_api_key_provider_entry()),
        credentials={"type": "API_KEY", "apiKey": "key-123"},
        connection_config={"domain": "scim.example.com"},
    )
    assert url == "https://scim.example.com/scim/Users?per_page=100"


def test_build_url_strips_slashes() -> None:
    url = build_proxy_url(
        _config(endpoint="/issues/", provider_entry={"proxy": {"base_url": "https://api.github.com/"}}),
        credentials={"type": "OAUTH2"},
        connection_config={},
    )
    assert url == "https://api.github.com/issues/"


def test_build_url_missing_base_raises() -> None:
    with pytest.raises(ProxyError, match="missing_api_url"):
        build_proxy_url(
            _config(endpoint="/test", provider_entry={"proxy": {}}),
            credentials={},
            connection_config={},
        )


# -- build_proxy_headers --


def test_headers_oauth2_bearer() -> None:
    headers = build_proxy_headers(
        _config(provider_entry=_oauth2_provider_entry()),
        url="https://api.github.com/repos",
        credentials={"type": "OAUTH2", "access_token": "gho_token"},
        connection_config={},
    )
    assert headers["authorization"] == "Bearer gho_token"


def test_headers_api_key_via_provider_template() -> None:
    headers = build_proxy_headers(
        _config(provider_entry=_api_key_provider_entry()),
        url="https://scim.example.com/scim/Users",
        credentials={"type": "API_KEY", "apiKey": "key-123"},
        connection_config={"domain": "scim.example.com"},
    )
    assert headers["authorization"] == "Bearer key-123"


def test_headers_basic_auth() -> None:
    headers = build_proxy_headers(
        _config(),
        url="https://api.example.com",
        credentials={"type": "BASIC", "username": "user", "password": "pass"},
        connection_config={},
    )
    import base64

    expected = base64.b64encode(b"user:pass").decode("ascii")
    assert headers["authorization"] == f"Basic {expected}"


def test_headers_app_bearer() -> None:
    headers = build_proxy_headers(
        _config(),
        url="https://api.example.com",
        credentials={"type": "APP", "access_token": "app-tok"},
        connection_config={},
    )
    assert headers["authorization"] == "Bearer app-tok"


def test_headers_forwarded_override_provider() -> None:
    headers = build_proxy_headers(
        _config(headers={"x-custom": "my-value", "authorization": "Bearer custom"}),
        url="https://api.example.com",
        credentials={"type": "OAUTH2", "access_token": "gho_token"},
        connection_config={},
    )
    assert headers["authorization"] == "Bearer custom"
    assert headers["x-custom"] == "my-value"


def test_headers_oauth2_cc_bearer_token() -> None:
    headers = build_proxy_headers(
        _config(),
        url="https://api.example.com",
        credentials={"type": "OAUTH2_CC", "token": "cc-tok"},
        connection_config={},
    )
    assert headers["authorization"] == "Bearer cc-tok"


def test_headers_oauth2_client_id_secret_interpolation() -> None:
    provider = {
        "auth_mode": "OAUTH2",
        "proxy": {
            "base_url": "https://api.example.com",
            "headers": {"x-client": "${clientId}", "x-secret": "${clientSecret}"},
        },
    }
    headers = build_proxy_headers(
        _config(provider_entry=provider),
        url="https://api.example.com/test",
        credentials={"type": "OAUTH2", "access_token": "tok"},
        connection_config={},
        integration_config={"oauth_client_id": "cid", "oauth_client_secret": "csec"},
    )
    assert headers["x-client"] == "cid"
    assert headers["x-secret"] == "csec"


# -- retry --


def _retry_config(provider_entry: dict[str, Any] | None = None) -> ProxyConfig:
    return _config(provider_entry=provider_entry or _oauth2_provider_entry())


def test_retry_network_error() -> None:
    result = get_proxy_retry_from_err(is_network_error=True, proxy_config=_retry_config())
    assert result.retry is True
    assert result.reason == "network_error"


def test_retry_500() -> None:
    result = get_proxy_retry_from_err(status=500, proxy_config=_retry_config())
    assert result.retry is True


def test_retry_429() -> None:
    result = get_proxy_retry_from_err(status=429, proxy_config=_retry_config())
    assert result.retry is True


def test_retry_401() -> None:
    result = get_proxy_retry_from_err(status=401, proxy_config=_retry_config())
    assert result.retry is True


def test_no_retry_200() -> None:
    result = get_proxy_retry_from_err(status=200, proxy_config=_retry_config())
    assert result.retry is False


def test_no_retry_404() -> None:
    result = get_proxy_retry_from_err(status=404, proxy_config=_retry_config())
    assert result.retry is False


def test_retry_on_header_match() -> None:
    # 404 is not retryable by default; retry_on makes it retryable
    result = get_proxy_retry_from_err(
        status=404, proxy_config=_retry_config(), retry_on=(404, 410)
    )
    assert result.retry is True
    assert result.reason == "retry_on_404"


def test_provider_error_code_exact_match() -> None:
    provider = {"proxy": {"base_url": "https://api.example.com", "retry": {"error_code": ["403"]}}}
    result = get_proxy_retry_from_err(status=403, proxy_config=_retry_config(provider))
    assert result.retry is True
    assert "403" in result.reason


def test_provider_error_code_xx_match() -> None:
    provider = {"proxy": {"base_url": "https://api.example.com", "retry": {"error_code": ["5xx"]}}}
    result = get_proxy_retry_from_err(status=503, proxy_config=_retry_config(provider))
    assert result.retry is True


def test_provider_error_code_range_match() -> None:
    provider = {
        "proxy": {"base_url": "https://api.example.com", "retry": {"error_code": ["500-502"]}}
    }
    result = get_proxy_retry_from_err(status=501, proxy_config=_retry_config(provider))
    assert result.retry is True


def test_provider_remaining_header_zero() -> None:
    provider = {
        "proxy": {
            "base_url": "https://api.example.com",
            "retry": {"remaining": "x-ratelimit-remaining"},
        }
    }
    result = get_proxy_retry_from_err(
        status=200,  # would normally not retry
        headers={"x-ratelimit-remaining": "0"},
        proxy_config=_retry_config(provider),
    )
    assert result.retry is True
    assert result.reason == "provider_remaining"


def test_backoff_wait_exponential() -> None:
    assert backoff_wait(1) == 0.5  # 500ms
    assert backoff_wait(2) == 1.0  # 1000ms
    assert backoff_wait(3) == 2.0  # 2000ms