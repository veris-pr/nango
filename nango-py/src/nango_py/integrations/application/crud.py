"""Integration CRUD use cases: create, quickstart, update (patch), delete.

Mirrors:
- ``packages/server/lib/controllers/integrations/postIntegration.ts`` (create + quickstart)
- ``packages/server/lib/controllers/integrations/uniqueKey/patchIntegration.ts`` (update)
- ``packages/server/lib/controllers/integrations/uniqueKey/deleteIntegration.ts`` (delete)

All use ``apiAuth`` + ``environment:integrations:write`` scope.
Response shape: ``integrationToPublicApi`` — the same ``ApiPublicIntegration``
used by the read endpoints.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.auth.domain.errors import Forbidden
from nango_py.integrations.application.gateway import (
    IntegrationRepository,
    ProviderCatalog,
)
from nango_py.integrations.application.get_integration import GetIntegration
from nango_py.integrations.domain.errors import (
    IntegrationNotFound,
    ProviderNotFound,
)
from nango_py.integrations.domain.integration import (
    Integration,
    PublicIntegrationView,
)

JsonObject = dict[str, Any]
WRITE_SCOPE = "environment:integrations:write"
QUICKSTART_AUTH_MODES = frozenset({"OAUTH1", "OAUTH2"})


@dataclass(frozen=True)
class CreateIntegrationRequest:
    context: AuthenticatedContext
    provider: str
    unique_key: str
    display_name: str | None = None
    forward_webhooks: bool = True
    credentials: JsonObject | None = None


@dataclass(frozen=True)
class PatchIntegrationRequest:
    context: AuthenticatedContext
    unique_key: str
    new_unique_key: str | None = None
    display_name: str | None = None
    forward_webhooks: bool | None = None
    credentials: JsonObject | None = None
    custom: JsonObject | None = None


@dataclass(frozen=True)
class DeleteIntegrationRequest:
    context: AuthenticatedContext
    unique_key: str


class IntegrationCrudService:
    """Create, update, delete integrations."""

    def __init__(
        self,
        *,
        integration_repository: IntegrationRepository,
        provider_catalog: ProviderCatalog,
        get_integration: GetIntegration,
    ) -> None:
        self._integrations = integration_repository
        self._providers = provider_catalog
        self._get_integration = get_integration

    async def execute_create(self, request: CreateIntegrationRequest) -> PublicIntegrationView:
        return await self.create(request)

    async def execute_patch(self, request: PatchIntegrationRequest) -> PublicIntegrationView:
        return await self.patch(request)

    async def execute_delete(self, request: DeleteIntegrationRequest) -> None:
        await self.delete(request)

    async def create(
        self, request: CreateIntegrationRequest
    ) -> PublicIntegrationView:
        _check_scope(request.context)

        provider = self._providers.get(request.provider)
        if provider is None:
            raise ProviderNotFound(request.provider)

        # Build the integration row
        integration_data: JsonObject = {
            "environment_id": request.context.environment.id,
            "provider": request.provider,
            "unique_key": request.unique_key,
            "display_name": request.display_name,
            "forward_webhooks": request.forward_webhooks,
            "missing_fields": [],
        }

        creds = request.credentials
        if creds:
            _apply_credentials(integration_data, creds)

        # Check for existing
        existing = await self._integrations.get_by_unique_key(
            environment_id=request.context.environment.id,
            unique_key=request.unique_key,
        )
        if existing is not None:
            from nango_py.integrations.domain.errors import (
    integration_already_exists,
)
            raise integration_already_exists(request.unique_key)

        # Create via repository — needs a create method
        integration = await self._create_integration(integration_data)

        return self._build_view(integration, provider)

    async def patch(
        self, request: PatchIntegrationRequest
    ) -> PublicIntegrationView:
        _check_scope(request.context)

        integration = await self._integrations.get_by_unique_key(
            environment_id=request.context.environment.id,
            unique_key=request.unique_key,
        )
        if integration is None:
            raise IntegrationNotFound(request.unique_key)

        provider = self._providers.get(integration.provider)
        if provider is None:
            raise ProviderNotFound(integration.provider)

        update_data: JsonObject = {}

        if request.new_unique_key and request.new_unique_key != request.unique_key:
            update_data["unique_key"] = request.new_unique_key

        if request.display_name is not None:
            update_data["display_name"] = request.display_name

        if request.forward_webhooks is not None:
            update_data["forward_webhooks"] = request.forward_webhooks

        if request.custom:
            update_data["custom"] = {**(integration.custom or {}), **request.custom}

        if request.credentials:
            if request.credentials.get("type") != provider.auth_mode:
                raise _invalid_body(
                    "incompatible credentials auth type and provider auth"
                )
            _apply_credentials(update_data, request.credentials)

        updated = await self._update_integration(integration.id, update_data)
        return self._build_view(updated, provider)

    async def delete(self, request: DeleteIntegrationRequest) -> bool:
        _check_scope(request.context)

        integration = await self._integrations.get_by_unique_key(
            environment_id=request.context.environment.id,
            unique_key=request.unique_key,
        )
        if integration is None:
            raise IntegrationNotFound(request.unique_key)

        await self._delete_integration(integration.id)
        return True

    def _build_view(
        self, integration: Integration, provider: Any
    ) -> PublicIntegrationView:
        display_name = integration.display_name or (
            provider.display_name if provider else integration.unique_key
        )
        return PublicIntegrationView(
            unique_key=integration.unique_key,
            provider=integration.provider,
            display_name=display_name,
            logo=f"{self._get_integration._base_public_url}/images/template-logos/{integration.provider}.svg",
            forward_webhooks=integration.forward_webhooks,
            created_at=integration.created_at,
            updated_at=integration.updated_at,
        )

    async def _create_integration(self, data: JsonObject) -> Integration:
        """Create an integration row in _nango_configs."""
        import json

        from sqlalchemy import text

        # Access the session factory through the repository
        repo = self._integrations
        sf = getattr(repo, "_session_factory", None)
        if sf is None:
            raise RuntimeError("repository has no _session_factory")

        async with sf() as session:
            row = (
                await session.execute(
                    text(
                        """
                        INSERT INTO _nango_configs
                        (unique_key, provider, environment_id, oauth_client_id,
                         oauth_client_secret, oauth_client_secret_iv, oauth_client_secret_tag,
                         oauth_scopes, app_link, custom, display_name, forward_webhooks,
                         shared_credentials_id, missing_fields, deleted)
                        VALUES (:uk, :prov, :eid, :cid, :csec, :iv, :tag,
                         :scopes, :app, :custom, :dn, :fw, NULL, :missing, false)
                        RETURNING *
                        """
                    ),
                    {
                        "uk": data.get("unique_key", ""),
                        "prov": data.get("provider", ""),
                        "eid": data.get("environment_id", 0),
                        "cid": data.get("oauth_client_id"),
                        "csec": data.get("oauth_client_secret"),
                        "iv": data.get("oauth_client_secret_iv"),
                        "tag": data.get("oauth_client_secret_tag"),
                        "scopes": data.get("oauth_scopes"),
                        "app": data.get("app_link"),
                        "custom": json.dumps(data.get("custom")) if data.get("custom") else None,
                        "dn": data.get("display_name"),
                        "fw": data.get("forward_webhooks", True),
                        "missing": data.get("missing_fields", []),
                    },
                )
            ).mappings().first()
            await session.commit()

        if row is None:
            raise RuntimeError("failed to create integration")
        return _integration_from_row(dict(row))

    async def _update_integration(
        self, integration_id: int, data: JsonObject
    ) -> Integration:
        """Update an integration row in _nango_configs."""
        import json
        from datetime import UTC, datetime

        from sqlalchemy import text

        repo = self._integrations
        sf = getattr(repo, "_session_factory", None)
        if sf is None:
            raise RuntimeError("repository has no _session_factory")

        set_clauses: list[str] = []
        params: dict[str, Any] = {"id": integration_id, "now": datetime.now(UTC)}

        for field, column in [
            ("unique_key", "unique_key"),
            ("display_name", "display_name"),
            ("forward_webhooks", "forward_webhooks"),
            ("oauth_client_id", "oauth_client_id"),
            ("oauth_client_secret", "oauth_client_secret"),
            ("oauth_scopes", "oauth_scopes"),
            ("app_link", "app_link"),
        ]:
            if field in data:
                set_clauses.append(f"{column} = :{field}")
                params[field] = data[field]

        if "custom" in data:
            set_clauses.append("custom = CAST(:custom AS jsonb)")
            params["custom"] = json.dumps(data["custom"])

        set_clauses.append("updated_at = :now")

        if not set_clauses:
            # No fields to update — just return the existing
            existing = await self._integrations.get_by_unique_key(
                environment_id=0, unique_key=""
            )
            if existing is None:
                raise RuntimeError("integration not found")
            return existing

        query = f"""
            UPDATE _nango_configs SET {", ".join(set_clauses)}
            WHERE id = :id
            RETURNING *
        """
        async with sf() as session:
            row = (
                await session.execute(text(query), params)
            ).mappings().first()
            await session.commit()

        if row is None:
            raise RuntimeError("failed to update integration")
        return _integration_from_row(dict(row))

    async def _delete_integration(self, integration_id: int) -> None:
        """Soft-delete an integration row."""
        from datetime import UTC, datetime

        from sqlalchemy import text

        repo = self._integrations
        sf = getattr(repo, "_session_factory", None)
        if sf is None:
            raise RuntimeError("repository has no _session_factory")

        async with sf() as session:
            await session.execute(
                text(
                    """
                    UPDATE _nango_configs
                    SET deleted = true, deleted_at = :now, updated_at = :now
                    WHERE id = :id
                    """
                ),
                {"id": integration_id, "now": datetime.now(UTC)},
            )
            await session.commit()


def _check_scope(context: AuthenticatedContext) -> None:
    if not context.scopes.has(WRITE_SCOPE):
        raise Forbidden((WRITE_SCOPE,))


def _apply_credentials(data: JsonObject, creds: JsonObject) -> None:
    """Apply credentials to integration data based on auth type."""
    cred_type = creds.get("type")
    if cred_type in ("OAUTH1", "OAUTH2"):
        data["oauth_client_id"] = creds.get("client_id", "")
        data["oauth_client_secret"] = creds.get("client_secret", "")
        data["oauth_scopes"] = creds.get("scopes", "")
        if creds.get("webhook_secret"):
            data["custom"] = {"webhookSecret": creds["webhook_secret"]}
    elif cred_type == "APP":
        data["oauth_client_id"] = creds.get("app_id", "")
        private_key = creds.get("private_key", "")
        data["oauth_client_secret"] = base64.b64encode(
            private_key.encode()
        ).decode()
        data["app_link"] = creds.get("app_link", "")
    elif cred_type == "CUSTOM":
        data["oauth_client_id"] = creds.get("client_id", "")
        data["oauth_client_secret"] = creds.get("client_secret", "")
        data["app_link"] = creds.get("app_link", "")
        data["custom"] = {
            "app_id": creds.get("app_id", ""),
            "private_key": base64.b64encode(
                creds.get("private_key", "").encode()
            ).decode(),
        }


def _invalid_body(message: str) -> Any:
    from nango_py.shared.errors import ValidationApiError
    return ValidationApiError(
        "invalid_body",
        [{"code": "custom", "message": message, "path": []}],
    )


def _integration_from_row(row: dict[str, Any]) -> Integration:
    """Build an Integration from a DB row (minimal fields for the view)."""
    from datetime import UTC, datetime

    from nango_py.integrations.domain.integration import Integration

    created = row.get("created_at")
    updated = row.get("updated_at")
    if not isinstance(created, datetime):
        created = datetime.now(UTC)
    if not isinstance(updated, datetime):
        updated = datetime.now(UTC)

    return Integration(
        id=row.get("id", 0),
        unique_key=row.get("unique_key", ""),
        provider=row.get("provider", ""),
        environment_id=row.get("environment_id", 0),
        created_at=created,
        updated_at=updated,
        oauth_client_id=row.get("oauth_client_id"),
        oauth_client_secret=row.get("oauth_client_secret"),
        oauth_scopes=row.get("oauth_scopes"),
        app_link=row.get("app_link"),
        display_name=row.get("display_name"),
        forward_webhooks=row.get("forward_webhooks", True),
        shared_credentials_id=row.get("shared_credentials_id"),
    )