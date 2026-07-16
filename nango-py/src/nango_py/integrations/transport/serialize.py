"""Serialize :class:`PublicIntegrationView` to the TypeScript wire shape.

``NOT_SET`` fields are omitted entirely (distinct from ``None``, which
serializes to JSON ``null``). Timestamps use ISO 8601 with a ``Z`` suffix to
match ``Date.toISOString()``; the differential harness normalizes precision.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from nango_py.integrations.domain.integration import (
    NOT_SET,
    CredentialsView,
    OAuthCredentials,
    PublicIntegrationView,
    _NotSet,
)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _serialize_credentials(credentials: CredentialsView | None) -> dict[str, Any] | None:
    if credentials is None:
        return None
    if isinstance(credentials, OAuthCredentials):
        return {
            "type": credentials.type,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
            "webhook_secret": credentials.webhook_secret,
        }
    return {
        "type": credentials.type,
        "app_id": credentials.app_id,
        "private_key": credentials.private_key,
        "app_link": credentials.app_link,
    }


def view_to_dict(view: PublicIntegrationView) -> dict[str, Any]:
    data: dict[str, Any] = {
        "unique_key": view.unique_key,
        "provider": view.provider,
        "display_name": view.display_name,
        "logo": view.logo,
        "forward_webhooks": view.forward_webhooks,
        "created_at": _iso(view.created_at),
        "updated_at": _iso(view.updated_at),
    }
    if not isinstance(view.webhook_url, _NotSet):
        data["webhook_url"] = view.webhook_url
    if not isinstance(view.credentials, _NotSet):
        data["credentials"] = _serialize_credentials(view.credentials)
    return data


def serialize_view(view: PublicIntegrationView) -> dict[str, Any]:
    return {"data": view_to_dict(view)}


__all__ = ["NOT_SET", "serialize_view", "view_to_dict"]