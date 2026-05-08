from __future__ import annotations

from nango.contracts import AsyncActionWebhookPayload, AuthWebhookPayload, SyncWebhookPayload
from nango.utils.result import Err
from nango.webhooks import (
    InMemoryCircuitBreaker,
    WebhookHTTPStatusError,
    WebhookRequest,
    WebhookResponse,
    deliver_webhook,
    signature_headers,
)
from nango.webhooks.circuit_breaker import CircuitOpenError


async def no_sleep(_seconds: float) -> None:
    return None


def test_signature_headers_match_existing_crypto_contract() -> None:
    assert signature_headers("secret", "payload") == {
        "X-Nango-Signature": "22439a879b090cd05e5b51c5b5d7e4a205830e6ab4f54b90f5a822b7c7110934",
        "X-Nango-Hmac-Sha256": "b82fcb791acec57859b989b430a826488ce2e479fdf92326bd0a2e8375a42ba4",
    }


async def test_successful_delivery_sends_stable_json_and_signature_headers() -> None:
    requests: list[WebhookRequest] = []

    async def sender(request: WebhookRequest) -> WebhookResponse:
        requests.append(request)
        return WebhookResponse(status_code=204)

    payload = AuthWebhookPayload(
        connectionId="conn-1",
        providerConfigKey="hubspot",
        authMode="OAUTH2",
        provider="hubspot",
        environment="dev",
        operation="creation",
        success=True,
    )

    result = await deliver_webhook(
        url="https://example.test/webhook",
        payload=payload,
        secret="secret",
        sender=sender,
    )

    assert result.is_ok()
    assert requests[0].body == (
        '{"authMode":"OAUTH2","connectionId":"conn-1","environment":"dev",'
        '"from":"nango","operation":"creation","provider":"hubspot",'
        '"providerConfigKey":"hubspot","success":true,"type":"auth"}'
    )
    assert requests[0].headers["X-Nango-Hmac-Sha256"] == signature_headers(
        "secret", requests[0].body
    )["X-Nango-Hmac-Sha256"]


async def test_delivery_retries_retryable_status_then_succeeds() -> None:
    attempts = 0

    def sender(_request: WebhookRequest) -> WebhookResponse:
        nonlocal attempts
        attempts += 1
        return WebhookResponse(status_code=503 if attempts == 1 else 200)

    result = await deliver_webhook(
        url="https://example.test/webhook",
        payload=SyncWebhookPayload(
            connectionId="conn-1",
            providerConfigKey="github",
            syncName="issues",
            syncVariant="base",
            model="Issue",
            syncType="INCREMENTAL",
            success=True,
        ),
        secret="secret",
        sender=sender,
        sleep=no_sleep,
    )

    assert result.is_ok()
    assert attempts == 2


async def test_delivery_does_not_retry_permanent_status() -> None:
    attempts = 0

    def sender(_request: WebhookRequest) -> WebhookResponse:
        nonlocal attempts
        attempts += 1
        return WebhookResponse(status_code=400)

    result = await deliver_webhook(
        url="https://example.test/webhook",
        payload={"type": "sync", "success": True},
        secret="secret",
        sender=sender,
        sleep=no_sleep,
    )

    assert isinstance(result, Err)
    assert isinstance(result.error, WebhookHTTPStatusError)
    assert attempts == 1


async def test_open_circuit_skips_sender() -> None:
    circuit_breaker = InMemoryCircuitBreaker(failure_threshold=1)
    calls = 0

    def failing_sender(_request: WebhookRequest) -> WebhookResponse:
        nonlocal calls
        calls += 1
        return WebhookResponse(status_code=503)

    first = await deliver_webhook(
        url="https://example.test/webhook",
        payload=AsyncActionWebhookPayload(
            connectionId="conn-1",
            providerConfigKey="github",
            payload={"id": "action-1"},
        ),
        secret="secret",
        sender=failing_sender,
        circuit_breaker=circuit_breaker,
        max_attempts=1,
    )
    second = await deliver_webhook(
        url="https://example.test/webhook",
        payload={"type": "async_action"},
        secret="secret",
        sender=failing_sender,
        circuit_breaker=circuit_breaker,
        max_attempts=1,
    )

    assert first.is_err()
    assert isinstance(second, Err)
    assert isinstance(second.error, CircuitOpenError)
    assert calls == 1
