"""Serialize connection views to the TypeScript wire shape.

List response: ``{connections: [ApiPublicConnection, ...]}`` (key is
``connections``, not ``data``). Single response: ``ApiPublicConnectionFull``
as a top-level object (not wrapped). ``errors`` items are ``{type, log_id}``.
"""

from __future__ import annotations

from typing import Any

from nango_py.connections.domain.connection import (
    ConnectionActiveLog,
    ConnectionEndUser,
    ConnectionFull,
    ConnectionListItem,
)

JsonObject = dict[str, Any]


def _serialize_active_logs(logs: list[ConnectionActiveLog]) -> list[dict[str, str]]:
    return [{"type": log.type, "log_id": log.log_id} for log in logs]


def _serialize_end_user(end_user: ConnectionEndUser | None) -> dict[str, Any] | None:
    if end_user is None:
        return None
    organization: dict[str, Any] | None = None
    if end_user.organization is not None:
        organization = {
            "id": end_user.organization.id,
            "display_name": end_user.organization.display_name,
        }
    return {
        "id": end_user.id,
        "display_name": end_user.display_name,
        "email": end_user.email,
        "tags": end_user.tags,
        "organization": organization,
    }


def list_item_to_dict(item: ConnectionListItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "connection_id": item.connection_id,
        "provider_config_key": item.provider_config_key,
        "provider": item.provider,
        "errors": _serialize_active_logs(item.errors),
        "end_user": _serialize_end_user(item.end_user),
        "tags": item.tags,
        "metadata": item.metadata,
        "created": item.created,
    }


def full_to_dict(full: ConnectionFull) -> dict[str, Any]:
    return {
        "id": full.id,
        "connection_id": full.connection_id,
        "provider_config_key": full.provider_config_key,
        "provider": full.provider,
        "errors": _serialize_active_logs(full.errors),
        "end_user": _serialize_end_user(full.end_user),
        "tags": full.tags,
        "metadata": full.metadata,
        "connection_config": full.connection_config,
        "created_at": full.created_at,
        "updated_at": full.updated_at,
        "last_fetched_at": full.last_fetched_at,
        "credentials": full.credentials,
    }


def serialize_list(items: list[ConnectionListItem]) -> dict[str, Any]:
    return {"connections": [list_item_to_dict(item) for item in items]}


__all__: list[Any] = [
    "full_to_dict",
    "list_item_to_dict",
    "serialize_list",
]