from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from nango.contracts.base import ContractModel
from nango.contracts.connect import ConnectSessionCreateRequest
from nango.domain.models import DeployMetadata, IntegrationConfig


class DataEnvelope(ContractModel):
    data: dict[str, Any]


class ProviderListResponse(ContractModel):
    data: list[dict[str, Any]]


class ProviderResponse(ContractModel):
    data: dict[str, Any]


class IntegrationListResponse(ContractModel):
    data: list[IntegrationConfig]


class IntegrationResponse(ContractModel):
    data: IntegrationConfig


class PublicConnectionFull(ContractModel):
    id: int
    connection_id: str
    provider_config_key: str
    provider: str
    errors: list[PublicConnectionError] = Field(default_factory=list)
    end_user: PublicConnectionEndUser | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] | None = None
    connection_config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    last_fetched_at: datetime | None = None
    credentials: dict[str, Any] = Field(default_factory=dict)


class PublicConnectionError(ContractModel):
    type: str
    log_id: str


class PublicConnectionEndUserOrganization(ContractModel):
    id: str
    display_name: str | None = None


class PublicConnectionEndUser(ContractModel):
    id: str
    display_name: str | None = None
    email: str | None = None
    tags: dict[str, str] | None = None
    organization: PublicConnectionEndUserOrganization | None = None


class PublicConnection(ContractModel):
    id: int
    connection_id: str
    provider_config_key: str
    created: datetime
    metadata: dict[str, Any] | None = None
    provider: str
    errors: list[PublicConnectionError] = Field(default_factory=list)
    end_user: PublicConnectionEndUser | None = None
    tags: dict[str, str] = Field(default_factory=dict)


class PublicConnectionListResponse(ContractModel):
    connections: list[PublicConnection]


class ConnectSessionRecord(ContractModel):
    token: str
    expires_at: datetime = Field(alias="expiresAt")
    connect_link: str = Field(alias="connectLink")
    request: ConnectSessionCreateRequest


class ConnectSessionResponse(ContractModel):
    data: ConnectSessionRecord


class DeployValidationRequest(ContractModel):
    yaml: str | None = None
    nango_yaml: str | None = Field(default=None, alias="nangoYaml")


class DeployValidationData(ContractModel):
    valid: bool
    metadata: DeployMetadata | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class DeployValidationResponse(ContractModel):
    data: DeployValidationData


class TriggerConnectionInput(ContractModel):
    id: int = 1
    connection_id: str = Field(alias="connectionId", min_length=1)
    provider_config_key: str = Field(alias="providerConfigKey", min_length=1)
    environment_id: int = Field(default=1, alias="environmentId")


class SyncTriggerIdentifierInput(ContractModel):
    name: str = Field(min_length=1)
    variant: str = Field(default="base", min_length=1)


class SyncTriggerOptionsInput(ContractModel):
    reset: bool = False
    empty_cache: bool = Field(default=False, alias="emptyCache")


class SyncTriggerRequest(ContractModel):
    sync_id: str | None = Field(default=None, alias="syncId")
    sync_name: str = Field(alias="syncName", min_length=1)
    sync_variant: str = Field(default="base", alias="syncVariant", min_length=1)
    debug: bool = False
    connection: TriggerConnectionInput | None = None
    connection_id: str | None = Field(default=None, alias="connectionId")
    provider_config_key: str | None = Field(default=None, alias="providerConfigKey")
    environment_id: int = Field(default=1, alias="environmentId")


class PublicSyncTriggerRequest(ContractModel):
    sync_id: str | None = Field(default=None, alias="syncId")
    sync_name: str | None = Field(default=None, alias="syncName")
    sync_variant: str = Field(default="base", alias="syncVariant", min_length=1)
    debug: bool = False
    connection: TriggerConnectionInput | None = None
    connection_id: str | None = Field(default=None, alias="connectionId")
    provider_config_key: str | None = Field(default=None, alias="providerConfigKey")
    environment_id: int = Field(default=1, alias="environmentId")
    syncs: list[str | SyncTriggerIdentifierInput] | None = None
    opts: SyncTriggerOptionsInput | None = None
    full_resync: bool | None = None
    sync_mode: Literal[
        "incremental",
        "full_refresh",
        "full_refresh_and_clear_cache",
    ] | None = None


class ActionTriggerRequest(ContractModel):
    action_name: str = Field(alias="actionName", min_length=1)
    activity_log_id: str | None = Field(default=None, alias="activityLogId")
    input: Any = None
    async_: bool = Field(default=False, alias="async")
    retry_max: int = Field(default=0, alias="retryMax", ge=0, le=5)
    connection: TriggerConnectionInput | None = None
    connection_id: str | None = Field(default=None, alias="connectionId")
    provider_config_key: str | None = Field(default=None, alias="providerConfigKey")
    environment_id: int = Field(default=1, alias="environmentId")


class TriggerTaskData(ContractModel):
    task_id: str = Field(alias="taskId")
    retry_key: str = Field(alias="retryKey")
    type: Literal["sync", "action"]


class TriggerTaskResponse(ContractModel):
    data: TriggerTaskData


class SuccessResponse(ContractModel):
    success: bool
