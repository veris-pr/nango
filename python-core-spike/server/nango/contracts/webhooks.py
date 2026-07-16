from typing import Any, Literal

from pydantic import Field

from nango.contracts.base import ContractModel


class WebhookSignatureHeaders(ContractModel):
    hmac_sha256: str = Field(alias="X-Nango-Hmac-Sha256")
    legacy_signature: str | None = Field(default=None, alias="X-Nango-Signature")


class WebhookSignatureFixture(ContractModel):
    description: str
    body: str
    secret: str
    headers: WebhookSignatureHeaders
    algorithm: Literal["HMAC-SHA256"]


class AuthWebhookPayload(ContractModel):
    from_: Literal["nango"] = Field(default="nango", alias="from")
    type: Literal["auth"] = "auth"
    connection_id: str = Field(alias="connectionId")
    provider_config_key: str = Field(alias="providerConfigKey")
    auth_mode: str = Field(alias="authMode")
    provider: str
    environment: str
    operation: Literal["creation", "override", "refresh"]
    success: bool
    error: dict[str, Any] | None = None


class SyncResponseResults(ContractModel):
    added: int
    updated: int
    deleted: int = 0


class SyncWebhookPayload(ContractModel):
    from_: Literal["nango"] = Field(default="nango", alias="from")
    type: Literal["sync"] = "sync"
    connection_id: str = Field(alias="connectionId")
    provider_config_key: str = Field(alias="providerConfigKey")
    sync_name: str = Field(alias="syncName")
    sync_variant: str = Field(alias="syncVariant")
    model: str
    sync_type: str = Field(alias="syncType")
    success: bool
    response_results: SyncResponseResults | None = Field(default=None, alias="responseResults")
    modified_after: str | None = Field(default=None, alias="modifiedAfter")
    query_time_stamp: str | None = Field(default=None, alias="queryTimeStamp")
    error: dict[str, Any] | None = None
    started_at: str | None = Field(default=None, alias="startedAt")
    failed_at: str | None = Field(default=None, alias="failedAt")


class AsyncActionWebhookPayload(ContractModel):
    from_: Literal["nango"] = Field(default="nango", alias="from")
    type: Literal["async_action"] = "async_action"
    connection_id: str = Field(alias="connectionId")
    provider_config_key: str = Field(alias="providerConfigKey")
    payload: dict[str, Any]
