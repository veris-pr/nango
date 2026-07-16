"""GetIntegration use case — behavior verified with fakes against the frozen contract."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from nango_py.auth.domain.context import (
    Account,
    ApiSecret,
    AuthenticatedContext,
    Environment,
    Scopes,
)
from nango_py.auth.domain.errors import Forbidden
from nango_py.integrations.application.get_integration import (
    GetIntegration,
    GetIntegrationRequest,
)
from nango_py.integrations.domain.errors import IntegrationNotFound, ProviderNotFound
from nango_py.integrations.domain.integration import (
    NOT_SET,
    AppCredentials,
    Integration,
    OAuthCredentials,
)
from nango_py.integrations.domain.provider import Provider

CREATED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
UPDATED_AT = datetime(2026, 1, 3, 4, 5, 6, tzinfo=UTC)
BASE_PUBLIC_URL = "https://public.example"
WEBHOOK_RECEIVE_URL = "https://webhook.example"

READ = ("environment:integrations:read",)
READ_CREDENTIALS = ("environment:integrations:read_credentials",)
WILDCARD = ("environment:*",)
CONNECTIONS_READ = ("environment:connections:read",)


class FakeIntegrationRepository:
    def __init__(self, rows: dict[tuple[int, str], Integration]) -> None:
        self._rows = rows

    async def get_by_unique_key(
        self, *, environment_id: int, unique_key: str
    ) -> Integration | None:
        return self._rows.get((environment_id, unique_key))

    async def list_for_environment(self, *, environment_id: int) -> list[Integration]:
        return [row for (env_id, _), row in self._rows.items() if env_id == environment_id]


class FakeProviderCatalog:
    def __init__(self, providers: dict[str, Provider]) -> None:
        self._providers = providers

    def get(self, name: str) -> Provider | None:
        return self._providers.get(name)

    def entry(self, name: str) -> dict[str, object] | None:
        return None

    def entries(self) -> dict[str, dict[str, object]]:
        return {}


def _account() -> Account:
    return Account(id=1, name="test-team", uuid="acc-uuid")


def _environment() -> Environment:
    return Environment(
        id=1, name="dev", account_id=1, uuid="env-uuid", is_production=False
    )


def _secret() -> ApiSecret:
    return ApiSecret(
        id=7,
        environment_id=1,
        display_name="default",
        secret="plain-secret",
        hashed="hashed",
        is_default=True,
    )


def _context(scopes: tuple[str, ...], source: str = "customer_key") -> AuthenticatedContext:
    return AuthenticatedContext(
        account=_account(),
        environment=_environment(),
        secret=_secret(),
        auth_source=source,  # type: ignore[arg-type]
        scopes=Scopes(scopes),
    )


def _integration(**overrides: Any) -> Integration:
    base = Integration(
        id=100,
        unique_key="github",
        provider="github",
        environment_id=1,
        created_at=CREATED_AT,
        updated_at=UPDATED_AT,
        oauth_client_id="client-123",
        oauth_client_secret="secret-456",
        oauth_scopes="repo,user",
        display_name="GitHub",
        forward_webhooks=True,
        shared_credentials_id=None,
    )
    return replace(base, **overrides) if overrides else base


def _provider(**overrides: Any) -> Provider:
    base = Provider(
        name="github",
        display_name="GitHub",
        auth_mode="OAUTH2",
        webhook_routing_script="githubWebhookRouting.js",
    )
    return replace(base, **overrides) if overrides else base


def _use_case(
    integrations: dict[tuple[int, str], Integration] | None = None,
    providers: dict[str, Provider] | None = None,
) -> GetIntegration:
    return GetIntegration(
        integration_repository=FakeIntegrationRepository(integrations or {}),
        provider_catalog=FakeProviderCatalog(providers or {}),
        base_public_url=BASE_PUBLIC_URL,
        webhook_receive_url=WEBHOOK_RECEIVE_URL,
    )


def _request(
    unique_key: str, include: frozenset[str], scopes: tuple[str, ...]
) -> GetIntegrationRequest:
    return GetIntegrationRequest(
        unique_key=unique_key,
        include=frozenset(include),  # type: ignore[arg-type]
        context=_context(scopes),
    )


async def test_forbidden_when_no_matching_scope() -> None:
    use_case = _use_case()
    request = _request("github", frozenset(), CONNECTIONS_READ)

    with pytest.raises(Forbidden) as exc:
        await use_case.execute(request)

    assert exc.value.status == 403
    assert exc.value.code == "forbidden"
    assert "environment:integrations:read" in exc.value.message
    assert "environment:integrations:read_credentials" in exc.value.message


async def test_integration_not_found() -> None:
    use_case = _use_case(providers={"github": _provider()})
    request = _request("ghost", frozenset(), READ)

    with pytest.raises(IntegrationNotFound) as exc:
        await use_case.execute(request)

    assert exc.value.status == 404
    assert exc.value.code == "not_found"
    assert exc.value.message == 'Integration "ghost" does not exist'


async def test_provider_not_found() -> None:
    use_case = _use_case(
        integrations={(1, "ghost"): replace(_integration(), unique_key="ghost", provider="ghost")},
    )
    request = _request("ghost", frozenset(), READ)

    with pytest.raises(ProviderNotFound) as exc:
        await use_case.execute(request)

    assert exc.value.status == 404
    assert exc.value.message == "Unknown provider ghost"


async def test_success_no_include_omits_optional_keys() -> None:
    use_case = _use_case(
        integrations={(1, "github"): _integration()},
        providers={"github": _provider()},
    )
    view = await use_case.execute(_request("github", frozenset(), READ))

    assert view.webhook_url is NOT_SET
    assert view.credentials is NOT_SET
    assert view.unique_key == "github"
    assert view.display_name == "GitHub"
    assert view.logo == f"{BASE_PUBLIC_URL}/images/template-logos/github.svg"
    assert view.forward_webhooks is True
    assert view.created_at == CREATED_AT
    assert view.updated_at == UPDATED_AT


async def test_success_webhook_include_with_routing_script() -> None:
    use_case = _use_case(
        integrations={(1, "github"): _integration()},
        providers={"github": _provider()},
    )
    view = await use_case.execute(
        _request("github", frozenset({"webhook"}), READ)
    )

    assert view.webhook_url == f"{WEBHOOK_RECEIVE_URL}/env-uuid/github"


async def test_success_webhook_include_without_routing_script_is_none() -> None:
    use_case = _use_case(
        integrations={(1, "github"): _integration()},
        providers={"github": _provider(webhook_routing_script=None)},
    )
    view = await use_case.execute(
        _request("github", frozenset({"webhook"}), READ)
    )

    assert view.webhook_url is None


async def test_credentials_omitted_when_read_scope_only() -> None:
    use_case = _use_case(
        integrations={(1, "github"): _integration()},
        providers={"github": _provider()},
    )
    view = await use_case.execute(
        _request("github", frozenset({"credentials"}), READ)
    )

    assert view.credentials is NOT_SET


async def test_credentials_oauth2_with_read_credentials_scope() -> None:
    custom: dict[str, object] = {"webhookSecret": "wh-secret-abc"}
    use_case = _use_case(
        integrations={(1, "github"): replace(_integration(), custom=custom)},
        providers={"github": _provider()},
    )
    view = await use_case.execute(
        _request("github", frozenset({"credentials"}), READ_CREDENTIALS)
    )

    assert isinstance(view.credentials, OAuthCredentials)
    assert view.credentials.type == "OAUTH2"
    assert view.credentials.client_id == "client-123"
    assert view.credentials.client_secret == "secret-456"
    assert view.credentials.scopes == "repo,user"
    assert view.credentials.webhook_secret == "wh-secret-abc"


async def test_credentials_empty_when_shared_credentials_id_set() -> None:
    use_case = _use_case(
        integrations={(1, "github"): replace(_integration(), shared_credentials_id=55)},
        providers={"github": _provider()},
    )
    view = await use_case.execute(
        _request("github", frozenset({"credentials"}), READ_CREDENTIALS)
    )

    assert isinstance(view.credentials, OAuthCredentials)
    assert view.credentials.client_id == ""
    assert view.credentials.client_secret == ""


async def test_credentials_app_mode_mapping() -> None:
    integration = replace(
        _integration(),
        unique_key="github-app",
        provider="github-app",
        oauth_client_id="app-id-123",
        oauth_client_secret="-----BEGIN RSA PRIVATE KEY-----\n-----END RSA PRIVATE KEY-----",
        app_link="https://example.com/install",
    )
    use_case = _use_case(
        integrations={(1, "github-app"): integration},
        providers={"github-app": _provider(
            name="github-app", auth_mode="APP", webhook_routing_script=None
        )},
    )
    view = await use_case.execute(
        _request("github-app", frozenset({"credentials"}), READ_CREDENTIALS)
    )

    assert isinstance(view.credentials, AppCredentials)
    assert view.credentials.type == "APP"
    assert view.credentials.app_id == "app-id-123"
    assert view.credentials.app_link == "https://example.com/install"


async def test_wildcard_scope_grants_read_credentials() -> None:
    use_case = _use_case(
        integrations={(1, "github"): _integration()},
        providers={"github": _provider()},
    )
    view = await use_case.execute(
        _request("github", frozenset({"credentials"}), WILDCARD)
    )

    assert isinstance(view.credentials, OAuthCredentials)


async def test_display_name_falls_back_to_provider() -> None:
    use_case = _use_case(
        integrations={(1, "github"): replace(_integration(), display_name=None)},
        providers={"github": _provider(display_name="GitHub Provider Default")},
    )
    view = await use_case.execute(_request("github", frozenset(), READ))

    assert view.display_name == "GitHub Provider Default"


async def test_credentials_none_for_unrecognized_auth_mode() -> None:
    use_case = _use_case(
        integrations={(1, "github"): _integration()},
        providers={"github": _provider(auth_mode="NONE")},
    )
    view = await use_case.execute(
        _request("github", frozenset({"credentials"}), READ_CREDENTIALS)
    )

    assert view.credentials is None