"""Integration domain model and public read view.

Mirrors the subset of ``IntegrationConfig`` (``packages/types/lib/integration/db.ts``)
and ``ApiPublicIntegration`` / ``ApiPublicIntegrationInclude``
(``packages/types/lib/integration/api.ts``) needed for the
``GET /integrations/:uniqueKey`` boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Integration:
    """Decrypted integration config row from ``_nango_configs``."""

    id: int
    unique_key: str
    provider: str
    environment_id: int
    created_at: datetime
    updated_at: datetime
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_scopes: str | None = None
    app_link: str | None = None
    custom: dict[str, object] = field(default_factory=dict)
    display_name: str | None = None
    forward_webhooks: bool = True
    shared_credentials_id: int | None = None


class _NotSet:
    """Marker for an optional response key omitted from the wire body.

    Distinct from ``None``: ``None`` serializes to JSON ``null`` while a
    ``_NotSet`` field is dropped entirely, matching the TypeScript handler's
    conditional key assignment.
    """

    __slots__ = ()


NOT_SET: _NotSet = _NotSet()


@dataclass(frozen=True)
class OAuthCredentials:
    type: str
    client_id: str
    client_secret: str
    scopes: str | None
    webhook_secret: str | None


@dataclass(frozen=True)
class AppCredentials:
    type: str
    app_id: str
    private_key: str
    app_link: str | None


CredentialsView = OAuthCredentials | AppCredentials


@dataclass(frozen=True)
class PublicIntegrationView:
    unique_key: str
    provider: str
    display_name: str
    logo: str
    forward_webhooks: bool
    created_at: datetime
    updated_at: datetime
    webhook_url: str | None | _NotSet = NOT_SET
    credentials: CredentialsView | None | _NotSet = NOT_SET