from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nango.contracts import (
    ConnectSessionCreateRequest,
    ConnectSessionCreateResponse,
    HealthResponse,
    UserCreatedEvent,
    WebhookSignatureFixture,
)


def test_health_response_uses_json_field_names() -> None:
    response = HealthResponse(status="ok", service="nango-python-core")

    assert response.model_dump(mode="json") == {
        "status": "ok",
        "service": "nango-python-core",
        "cutover_mode": "disabled",
    }


def test_connect_session_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ConnectSessionCreateRequest.model_validate(
            {
                "end_user": {"id": "user-123"},
                "unexpected": True,
            }
        )


def test_connect_session_response_serializes_datetime_as_json_string() -> None:
    response = ConnectSessionCreateResponse.model_validate(
        {
            "data": {
                "token": "connect-token",
                "connect_link": "https://connect.nango.dev/session/connect-token",
                "expires_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
            }
        }
    )

    assert response.model_dump(mode="json") == {
        "data": {
            "token": "connect-token",
            "connect_link": "https://connect.nango.dev/session/connect-token",
            "expires_at": "2025-01-02T03:04:05Z",
        }
    }


def test_pubsub_event_preserves_camel_case_wire_fields() -> None:
    event = UserCreatedEvent.model_validate(
        {
            "idempotencyKey": "user-1-created",
            "subject": "user",
            "type": "user.created",
            "payload": {"userId": 1, "teamId": 2},
            "createdAt": "2025-01-02T03:04:05Z",
        }
    )

    assert event.model_dump(mode="json", by_alias=True, exclude_none=True) == {
        "idempotencyKey": "user-1-created",
        "subject": "user",
        "type": "user.created",
        "payload": {"userId": 1, "teamId": 2},
        "createdAt": "2025-01-02T03:04:05Z",
    }


def test_webhook_signature_fixture_preserves_header_names() -> None:
    fixture = WebhookSignatureFixture.model_validate(
        {
            "description": "fixture",
            "body": "{}",
            "secret": "fixture-secret",
            "headers": {"X-Nango-Hmac-Sha256": "sha256=fixture"},
            "algorithm": "HMAC-SHA256",
        }
    )

    assert fixture.model_dump(mode="json", by_alias=True, exclude_none=True)["headers"] == {
        "X-Nango-Hmac-Sha256": "sha256=fixture"
    }
