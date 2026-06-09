from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from nango.nango_yaml import ParsedNangoAction, ParsedNangoSync, ParsedNangoYaml


def utc_now() -> datetime:
    return datetime.now(UTC)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Account(DomainModel):
    id: int
    name: str
    uuid: str | None = None


class Environment(DomainModel):
    id: int
    account_id: int = Field(alias="accountId")
    name: str
    is_production: bool = Field(default=False, alias="isProduction")


class IntegrationConfig(DomainModel):
    id: int
    environment_id: int = Field(alias="environmentId")
    provider_config_key: str = Field(alias="providerConfigKey")
    provider: str
    oauth_client_id: str | None = Field(default=None, alias="oauthClientId")
    oauth_scopes: tuple[str, ...] = Field(default=(), alias="oauthScopes")
    forward_webhooks: bool = Field(default=True, alias="forwardWebhooks")
    missing_fields: tuple[str, ...] = Field(default=(), alias="missingFields")
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")
    updated_at: datetime = Field(default_factory=utc_now, alias="updatedAt")


class Connection(DomainModel):
    id: int
    environment_id: int = Field(alias="environmentId")
    config_id: int = Field(alias="configId")
    provider_config_key: str = Field(alias="providerConfigKey")
    connection_id: str = Field(alias="connectionId")
    credentials: dict[str, Any]
    connection_config: dict[str, Any] = Field(default_factory=dict, alias="connectionConfig")
    metadata: dict[str, Any] | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    private_key_id: int | None = Field(default=None, alias="privateKeyId")
    last_fetched_at: datetime | None = Field(default=None, alias="lastFetchedAt")
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")
    updated_at: datetime = Field(default_factory=utc_now, alias="updatedAt")


class ConnectionPrivateKey(DomainModel):
    key_value: str = Field(alias="keyValue")
    key_id: int = Field(alias="keyId")
    key_hash: str = Field(alias="keyHash")


class ConnectionUpsertResult(DomainModel):
    connection: Connection
    operation: Literal["creation", "override"]
    private_key: ConnectionPrivateKey | None = Field(default=None, alias="privateKey")


class SyncEndpoint(DomainModel):
    method: str
    path: str
    group: str | None = None


class DeployFlowMetadata(DomainModel):
    provider_config_key: str = Field(alias="providerConfigKey")
    name: str
    type: Literal["sync", "action"]
    models: tuple[str, ...] = ()
    input: str | None = None
    description: str = ""
    version: str = ""
    scopes: tuple[str, ...] = ()
    endpoints: tuple[SyncEndpoint, ...] = ()
    runs: str | None = None
    sync_type: Literal["full", "incremental"] | None = Field(default=None, alias="syncType")
    track_deletes: bool | None = Field(default=None, alias="trackDeletes")
    auto_start: bool | None = Field(default=None, alias="autoStart")
    webhook_subscriptions: tuple[str, ...] = Field(default=(), alias="webhookSubscriptions")
    features: tuple[str, ...] = ()


class DeployMetadata(DomainModel):
    flows: tuple[DeployFlowMetadata, ...]
    model_names: tuple[str, ...] = Field(alias="modelNames")

    @classmethod
    def from_parsed_nango_yaml(cls, parsed: ParsedNangoYaml) -> DeployMetadata:
        flows: list[DeployFlowMetadata] = []
        for integration in parsed.integrations:
            provider_config_key = integration.provider_config_key
            flows.extend(
                _sync_to_flow(provider_config_key, sync)
                for sync in integration.syncs
            )
            flows.extend(
                _action_to_flow(provider_config_key, action)
                for action in integration.actions
            )

        return cls(flows=tuple(flows), modelNames=tuple(parsed.models))


def _sync_to_flow(provider_config_key: str, sync: ParsedNangoSync) -> DeployFlowMetadata:
    return DeployFlowMetadata(
        providerConfigKey=provider_config_key,
        name=sync.name,
        type="sync",
        models=sync.output,
        input=sync.input,
        description=sync.description,
        version=sync.version,
        scopes=sync.scopes,
        endpoints=tuple(
            SyncEndpoint(method=endpoint.method, path=endpoint.path, group=endpoint.group)
            for endpoint in sync.endpoints
        ),
        runs=sync.runs,
        syncType=sync.sync_type,
        trackDeletes=sync.track_deletes,
        autoStart=sync.auto_start,
        webhookSubscriptions=sync.webhook_subscriptions,
        features=sync.features,
    )


def _action_to_flow(provider_config_key: str, action: ParsedNangoAction) -> DeployFlowMetadata:
    endpoints: tuple[SyncEndpoint, ...] = ()
    if action.endpoint is not None:
        endpoints = (
            SyncEndpoint(
                method=action.endpoint.method,
                path=action.endpoint.path,
                group=action.endpoint.group,
            ),
        )

    return DeployFlowMetadata(
        providerConfigKey=provider_config_key,
        name=action.name,
        type="action",
        models=action.output or (),
        input=action.input,
        description=action.description,
        version=action.version,
        scopes=action.scopes,
        endpoints=endpoints,
        features=action.features,
    )
