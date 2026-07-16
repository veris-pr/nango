from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from nango.utils.crypto import (
    hmac_sha256_hex,
    nango_webhook_signature_headers,
    verify_hmac_sha256_hex,
)
from nango.utils.errors import ApplicationError, ValidationIssue
from nango.utils.json import canonical_json, stable_json
from nango.utils.logging import JsonFormatter
from nango.utils.retry import retry

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "contract-fixtures"


def test_application_error_serializes_api_error_envelope() -> None:
    error = ApplicationError(
        "invalid_body",
        message="Request body is invalid",
        status_code=400,
        errors=(ValidationIssue("required", "Field is required", ("data", "token")),),
    )

    assert error.to_api_error() == {
        "error": {
            "code": "invalid_body",
            "message": "Request body is invalid",
            "errors": [
                {"code": "required", "message": "Field is required", "path": ["data", "token"]}
            ],
        }
    }


def test_retry_retries_retryable_exception_then_returns_value() -> None:
    attempts = 0
    delays: list[float] = []

    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("provider timed out")
        return "ok"

    assert retry(flaky, max_attempts=3, delay_seconds=0.25, sleep=delays.append) == "ok"
    assert attempts == 3
    assert delays == [0.25, 0.25]


def test_retry_stops_on_non_retryable_exception() -> None:
    attempts = 0

    def fail() -> str:
        nonlocal attempts
        attempts += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError, match="bad input"):
        retry(fail, max_attempts=3)

    assert attempts == 1


def test_stable_json_matches_webhook_delivery_ordering() -> None:
    assert stable_json({"type": "sync", "success": True}) == '{"success":true,"type":"sync"}'


def test_canonical_json_matches_contract_fixture_format() -> None:
    assert canonical_json({"b": 1, "a": {"d": 2, "c": 3}}) == (
        '{\n  "a": {\n    "c": 3,\n    "d": 2\n  },\n  "b": 1\n}\n'
    )


def test_hmac_helpers_match_webhook_fixture() -> None:
    fixture = json.loads((FIXTURE_DIR / "webhook.signature.fixture.json").read_text())
    headers = fixture["headers"]

    assert hmac_sha256_hex(fixture["secret"], fixture["body"]) == headers["X-Nango-Hmac-Sha256"]
    assert nango_webhook_signature_headers(fixture["secret"], fixture["body"]) == headers
    assert verify_hmac_sha256_hex(
        fixture["secret"],
        fixture["body"],
        headers["X-Nango-Hmac-Sha256"],
    )


def test_json_log_formatter_emits_structured_service_context() -> None:
    record = logging.LogRecord(
        name="nango.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="ready",
        args=(),
        exc_info=None,
    )

    payload = json.loads(JsonFormatter(service_name="test-core").format(record))

    assert payload["service"] == "test-core"
    assert payload["message"] == "ready"
