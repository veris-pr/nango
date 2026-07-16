from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import pytest

from nango.domain import (
    ConnectionService,
    DeployMetadataService,
    InMemoryConnectionRepository,
    InMemoryIntegrationConfigRepository,
    IntegrationConfigService,
    ProviderResolver,
    provider_not_found,
)
from nango.keystore import InMemoryPrivateKeyRepository
from nango.nango_yaml import parse_nango_yaml_text
from nango.utils.errors import ApplicationError

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "nango_yaml"


def providers() -> dict[str, dict[str, object]]:
    return {
        "github": {
            "auth_mode": "OAUTH2",
            "default_scopes": ["repo", "read:user"],
        }
    }


def integration_service() -> IntegrationConfigService:
    return IntegrationConfigService(
        provider_resolver=ProviderResolver(providers()),
    )


def test_integration_creation_and_lookup_resolves_provider_defaults() -> None:
    service = integration_service()

    integration = service.create_integration(
        environment_id=1,
        provider_config_key="github-demo",
        provider_name="github",
        oauth_client_id="client-id",
    )

    assert integration.provider == "github"
    assert integration.provider_config_key == "github-demo"
    assert integration.oauth_scopes == ("repo", "read:user")
    assert service.get_integration(
        environment_id=1,
        provider_config_key="github-demo",
    ) == integration


def test_connection_creation_update_and_private_key_integration() -> None:
    integration_repository = InMemoryIntegrationConfigRepository()
    IntegrationConfigService(
        repository=integration_repository,
        provider_resolver=ProviderResolver(providers()),
    ).create_integration(
        environment_id=1,
        provider_config_key="github-demo",
        provider_name="github",
        oauth_client_id="client-id",
    )
    connection_service = ConnectionService(
        integration_repository=integration_repository,
        connection_repository=InMemoryConnectionRepository(),
        private_key_repository=InMemoryPrivateKeyRepository(encryption_key="test-encryption-key"),
    )

    created = connection_service.upsert_connection(
        environment_id=1,
        provider_config_key="github-demo",
        connection_id="conn-1",
        credentials={"type": "OAUTH2", "access_token": "token-1"},
        metadata={"customer": "acme"},
        account_id=10,
        create_private_key=True,
    )
    updated = connection_service.upsert_connection(
        environment_id=1,
        provider_config_key="github-demo",
        connection_id="conn-1",
        credentials={"type": "OAUTH2", "access_token": "token-2"},
        tags={"tier": "enterprise"},
    )

    assert created.operation == "creation"
    assert created.private_key is not None
    assert created.private_key.key_value.startswith("nango_connection_")
    assert created.connection.private_key_id == created.private_key.key_id
    assert updated.operation == "override"
    assert updated.connection.id == created.connection.id
    assert updated.connection.credentials["access_token"] == "token-2"
    assert updated.connection.metadata == {"customer": "acme"}
    assert updated.connection.tags == {"tier": "enterprise"}


def test_provider_resolution_failure_raises_application_error() -> None:
    service = IntegrationConfigService(provider_resolver=ProviderResolver({}))

    with pytest.raises(ApplicationError) as raised:
        service.create_integration(
            environment_id=1,
            provider_config_key="missing",
            provider_name="missing-provider",
        )

    assert raised.value.code == "provider_not_found"
    assert raised.value.status_code == HTTPStatus.NOT_FOUND


def test_domain_error_serializes_application_error_envelope() -> None:
    error = provider_not_found("missing-provider")

    assert error.to_api_error() == {
        "error": {
            "code": "provider_not_found",
            "message": 'Provider "missing-provider" was not found',
        }
    }


def test_nango_yaml_deploy_metadata_ingestion() -> None:
    parsed = parse_nango_yaml_text((FIXTURE_DIR / "valid.v2.yaml").read_text())

    metadata = DeployMetadataService().from_parsed_nango_yaml(parsed)

    assert set(metadata.model_names) == {"GithubIssue", "GithubUser", "CreateIssueInput"}
    assert [flow.name for flow in metadata.flows] == ["issues", "createIssue"]
    assert metadata.flows[0].provider_config_key == "github-demo"
    assert metadata.flows[0].type == "sync"
    assert metadata.flows[0].models == ("GithubIssue",)
    assert metadata.flows[0].runs == "every day"
    assert metadata.flows[1].type == "action"
    assert metadata.flows[1].endpoints[0].method == "POST"
