"""Connect session use cases: create, get-by-token, delete.

Mirrors ``packages/server/lib/services/connectSession.service.ts`` +
``packages/server/lib/controllers/connect/postSessions.ts``.

CreateConnectSession:
  insert session row → create keystore token (entity_type='connect_session',
  entity_id=session.id, ttl=30min) → return (token, connect_link, expires_at).

GetConnectSessionByToken:
  keystore.get_private_key(token) → session.get_by_id(private_key.entity_id) →
  return session data.

DeleteConnectSession:
  keystore.delete_private_key + session.delete → 204.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.domain.errors import Forbidden
from nango_py.connect_sessions.application.gateway import ConnectSessionRepository
from nango_py.connect_sessions.domain.session import (
    ConnectSessionData,
    CreateConnectSessionResult,
)
from nango_py.keystore.application.gateway import PrivateKeyRepository
from nango_py.shared.serialize import iso_required

CONNECT_SESSION_TTL_MS = 30 * 60 * 1000  # 30 minutes
CONNECT_SESSION_SCOPE = "environment:connect_sessions:write"
CONNECT_URL_DEFAULT = "https://connect.nango.dev"

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class CreateConnectSessionRequest:
    context: AuthenticatedContext
    end_user: JsonObject | None = None
    organization: JsonObject | None = None
    allowed_integrations: list[str] | None = None
    integrations_config_defaults: JsonObject | None = None
    overrides: JsonObject | None = None
    tags: dict[str, str] | None = None
    connect_url: str = CONNECT_URL_DEFAULT


class CreateConnectSession:
    def __init__(
        self,
        *,
        session_repository: ConnectSessionRepository,
        private_key_repository: PrivateKeyRepository,
    ) -> None:
        self._sessions = session_repository
        self._keys = private_key_repository

    async def execute(self, request: CreateConnectSessionRequest) -> CreateConnectSessionResult:
        if not request.context.scopes.has(CONNECT_SESSION_SCOPE):
            raise Forbidden((CONNECT_SESSION_SCOPE,))

        end_user_data = None
        if request.end_user is not None:
            end_user_data = {**request.end_user}
            if request.organization:
                end_user_data["organization_id"] = request.organization.get("id")
                end_user_data["organization_display_name"] = (
            request.organization.get("display_name")
        )

        session = await self._sessions.create(
            account_id=request.context.account.id,
            environment_id=request.context.environment.id,
            allowed_integrations=request.allowed_integrations,
            integrations_config_defaults=request.integrations_config_defaults,
            end_user=end_user_data,
            tags=request.tags or {},
            overrides=request.overrides,
        )

        key_value, private_key = await self._keys.create_private_key(
            display_name="",
            entity_type="connect_session",
            entity_id=session.id,
            account_id=request.context.account.id,
            environment_id=request.context.environment.id,
            ttl_ms=CONNECT_SESSION_TTL_MS,
        )

        connect_link = f"{request.connect_url.rstrip('/')}/?session_token={key_value}"

        expires_at = iso_required(private_key.expires_at) if private_key.expires_at else ""
        return CreateConnectSessionResult(
            token=key_value,
            connect_link=connect_link,
            expires_at=expires_at,
        )


class GetConnectSessionByToken:
    def __init__(
        self,
        *,
        session_repository: ConnectSessionRepository,
        private_key_repository: PrivateKeyRepository,
    ) -> None:
        self._sessions = session_repository
        self._keys = private_key_repository

    async def execute(self, token: str) -> ConnectSessionData:
        private_key = await self._keys.get_private_key(token)
        if private_key is None:
            return None  # type: ignore[return-value]

        session = await self._sessions.get_by_id(
            id=private_key.entity_id,
            account_id=private_key.account_id,
            environment_id=private_key.environment_id,
        )
        if session is None:
            return None  # type: ignore[return-value]

        return ConnectSessionData(
            end_user=session.end_user,
            allowed_integrations=session.allowed_integrations,
            integrations_config_defaults=_transform_config_defaults(session.integrations_config_defaults),
            is_reconnecting=session.connection_id is not None,
            overrides=session.overrides,
        )


class DeleteConnectSession:
    def __init__(
        self,
        *,
        session_repository: ConnectSessionRepository,
        private_key_repository: PrivateKeyRepository,
    ) -> None:
        self._sessions = session_repository
        self._keys = private_key_repository

    async def execute(self, token: str) -> bool:
        private_key = await self._keys.get_private_key(token)
        if private_key is None:
            return False

        deleted = await self._sessions.delete(
            id=private_key.entity_id,
            account_id=private_key.account_id,
            environment_id=private_key.environment_id,
        )
        await self._keys.delete_private_key(
            key_value=token, entity_type="connect_session"
        )
        return deleted


def _transform_config_defaults(
    raw: JsonObject | None,
) -> JsonObject | None:
    if raw is None:
        return None
    result: JsonObject = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            result[key] = {
                "connection_config": value.get("connectionConfig"),
                "authorization_params": value.get("authorization_params"),
            }
    return result