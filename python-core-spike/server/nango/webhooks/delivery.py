from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from nango.contracts.base import ContractModel
from nango.utils.crypto import nango_webhook_signature_headers
from nango.utils.json import stable_json
from nango.utils.result import Err, Ok, Result
from nango.utils.retry import DEFAULT_RETRYABLE_STATUS_CODES, is_retryable_error
from nango.webhooks.circuit_breaker import CircuitOpenError, InMemoryCircuitBreaker

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_TIMEOUT_SECONDS = 10.0
WEBHOOK_CONTENT_TYPE = "application/json"
USER_AGENT = "nango-python-core/0.1.0"

type WebhookBody = ContractModel | Mapping[str, Any]
type WebhookSender = Callable[["WebhookRequest"], "WebhookResponse | Awaitable[WebhookResponse]"]
type AsyncSleep = Callable[[float], Awaitable[None]]


class WebhookDeliveryError(Exception):
    pass


class WebhookHTTPStatusError(WebhookDeliveryError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"webhook_status_{status_code}")
        self.status_code = status_code


type WebhookDeliveryFailure = WebhookDeliveryError | CircuitOpenError


@dataclass(frozen=True)
class WebhookRequest:
    url: str
    body: str
    headers: dict[str, str]
    timeout_seconds: float


@dataclass(frozen=True)
class WebhookResponse:
    status_code: int
    headers: Mapping[str, str] = field(default_factory=dict)


def signature_headers(secret: str, body: str) -> dict[str, str]:
    return nango_webhook_signature_headers(secret, body)


async def deliver_webhook(
    *,
    url: str,
    payload: WebhookBody,
    secret: str,
    sender: WebhookSender,
    circuit_breaker: InMemoryCircuitBreaker | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    retry_delay_seconds: float = 0,
    sleep: AsyncSleep = asyncio.sleep,
) -> Result[WebhookResponse, WebhookDeliveryFailure]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    body = _body_string(payload)
    request = WebhookRequest(
        url=url,
        body=body,
        headers={
            **signature_headers(secret, body),
            "content-type": WEBHOOK_CONTENT_TYPE,
            "user-agent": USER_AGENT,
        },
        timeout_seconds=timeout_seconds,
    )

    for attempt in range(1, max_attempts + 1):
        try:
            if circuit_breaker:
                circuit_breaker.before_request(url)

            response = await _send(sender, request)
            if 200 <= response.status_code < 300:
                if circuit_breaker:
                    circuit_breaker.record_success(url)
                return Ok(response)

            raise WebhookHTTPStatusError(response.status_code)
        except Exception as exc:
            delivery_error = _delivery_error(exc)

            if circuit_breaker and not isinstance(delivery_error, CircuitOpenError):
                circuit_breaker.record_failure(url)

            if attempt == max_attempts or not _should_retry(exc):
                return Err(delivery_error)

            await sleep(retry_delay_seconds)

    raise RuntimeError("unreachable")


def _body_string(payload: WebhookBody) -> str:
    if isinstance(payload, ContractModel):
        return stable_json(payload.model_dump(by_alias=True, exclude_none=True))
    return stable_json(payload)


async def _send(sender: WebhookSender, request: WebhookRequest) -> WebhookResponse:
    response = sender(request)
    if inspect.isawaitable(response):
        return await response
    return response


def _delivery_error(exc: Exception) -> WebhookDeliveryFailure:
    if isinstance(exc, WebhookDeliveryError):
        return exc
    if isinstance(exc, CircuitOpenError):
        return exc
    return WebhookDeliveryError(str(exc))


def _should_retry(exc: Exception) -> bool:
    return is_retryable_error(
        exc,
        retryable_exceptions=(ConnectionError, TimeoutError),
        retryable_status_codes=DEFAULT_RETRYABLE_STATUS_CODES,
    )
