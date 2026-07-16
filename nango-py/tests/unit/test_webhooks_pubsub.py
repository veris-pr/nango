"""Unit tests for webhooks (delivery, signatures, circuit breaker) and pubsub."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from nango_py.pubsub.events import InMemoryPubsubTransport, PubsubPublisher
from nango_py.shared.crypto import (
    hmac_sha256_hex,
    nango_webhook_signature_headers,
    stable_json,
    unsafe_legacy_sha256_hex,
)
from nango_py.webhooks.circuit_breaker import CircuitOpenError, InMemoryCircuitBreaker
from nango_py.webhooks.delivery import (
    WebhookHTTPStatusError,
    WebhookRequest,
    WebhookResponse,
    deliver_webhook,
)

# -- signatures --


def test_stable_json_sorts_keys() -> None:
    assert stable_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_hmac_matches_known_vector() -> None:
    result = hmac_sha256_hex("secret", "payload")
    assert len(result) == 64  # hex digest


def test_legacy_signature_matches_pattern() -> None:
    result = unsafe_legacy_sha256_hex("secret", "payload")
    assert len(result) == 64


def test_webhook_signature_headers_present() -> None:
    headers = nango_webhook_signature_headers("secret", "body")
    assert "X-Nango-Hmac-Sha256" in headers
    assert "X-Nango-Signature" in headers


# -- circuit breaker --


def test_circuit_opens_after_threshold() -> None:

    clock_calls = [0.0]

    def mock_clock() -> float:
        return clock_calls[0]

    breaker = InMemoryCircuitBreaker(
        failure_threshold=3, window_seconds=60, cooldown_seconds=30, clock=mock_clock
    )
    for _ in range(3):
        breaker.record_failure("https://example.com/hook")

    with pytest.raises(CircuitOpenError):
        breaker.before_request("https://example.com/hook")


def test_circuit_closes_after_cooldown() -> None:
    clock_calls = [0.0]

    def mock_clock() -> float:
        return clock_calls[0]

    breaker = InMemoryCircuitBreaker(
        failure_threshold=2, window_seconds=60, cooldown_seconds=30, clock=mock_clock
    )
    breaker.record_failure("url-1")
    clock_calls[0] = 0
    breaker.record_failure("url-1")
    with pytest.raises(CircuitOpenError):
        breaker.before_request("url-1")
    clock_calls[0] = 31  # after cooldown
    breaker.before_request("url-1")  # should not raise


# -- delivery --


async def _sync_sender(request: WebhookRequest) -> WebhookResponse:
    return WebhookResponse(status_code=200, headers={})


async def _fail_sender(request: WebhookRequest) -> WebhookResponse:
    raise ConnectionError("boom")


async def _status_sender(status: int) -> Any:
    async def _send(request: WebhookRequest) -> WebhookResponse:
        return WebhookResponse(status_code=status)
    return _send


async def test_delivery_success() -> None:
    result = await deliver_webhook(
        url="https://example.com/hook",
        payload={"type": "sync", "data": [1, 2]},
        secret="webhook-secret",
        sender=_sync_sender,
    )
    assert isinstance(result, WebhookResponse)
    assert result.status_code == 200


async def test_delivery_retries_on_500() -> None:
    calls = 0

    async def sender(request: WebhookRequest) -> WebhookResponse:
        nonlocal calls
        calls += 1
        if calls < 3:
            return WebhookResponse(status_code=503)
        return WebhookResponse(status_code=200)

    result = await deliver_webhook(
        url="https://example.com/hook",
        payload={"ok": True},
        secret="secret",
        sender=sender,
        max_attempts=3,
        sleep=lambda _: asyncio.sleep(0),
    )
    assert isinstance(result, WebhookResponse)
    assert result.status_code == 200
    assert calls == 3


async def test_delivery_does_not_retry_404() -> None:
    calls = 0

    async def sender(request: WebhookRequest) -> WebhookResponse:
        nonlocal calls
        calls += 1
        return WebhookResponse(status_code=404)

    result = await deliver_webhook(
        url="https://example.com/hook",
        payload={},
        secret="secret",
        sender=sender,
        max_attempts=3,
        sleep=lambda _: asyncio.sleep(0),
    )
    assert isinstance(result, WebhookHTTPStatusError)
    assert result.status_code == 404
    assert calls == 1


async def test_delivery_retries_network_error() -> None:
    calls = 0

    async def sender(request: WebhookRequest) -> WebhookResponse:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise ConnectionError("network down")
        return WebhookResponse(status_code=200)

    result = await deliver_webhook(
        url="https://example.com/hook",
        payload={},
        secret="secret",
        sender=sender,
        max_attempts=3,
        sleep=lambda _: asyncio.sleep(0),
    )
    assert isinstance(result, WebhookResponse)
    assert result.status_code == 200


# -- pubsub --


async def test_pubsub_publish_stores_event() -> None:
    transport = InMemoryPubsubTransport()
    publisher = PubsubPublisher(transport)
    await publisher.publish(
        subject="usage",
        type="usage.proxy",
        payload={"accountId": 1, "success": True},
    )
    assert len(transport.published) == 1
    event = transport.published[0]
    assert event.subject == "usage"
    assert event.type == "usage.proxy"
    assert event.payload["accountId"] == 1
    assert event.idempotency_key  # auto-generated


async def test_pubsub_publish_with_explicit_idempotency_key() -> None:
    transport = InMemoryPubsubTransport()
    publisher = PubsubPublisher(transport)
    await publisher.publish(
        subject="user",
        type="user.created",
        payload={"userId": "u-1", "teamId": "t-1"},
        idempotency_key="custom-key-123",
    )
    assert transport.published[0].idempotency_key == "custom-key-123"