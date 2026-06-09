from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from nango.contracts.base import ContractModel

AuthSource = Literal["customer_key", "api_secret", "env_var"]


class AccountSummary(ContractModel):
    id: int
    uuid: str | None = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class EnvironmentSummary(ContractModel):
    id: int
    uuid: str | None = None
    name: str
    account_id: int = Field(alias="accountId")
    public_key: str | None = Field(default=None, alias="publicKey")
    secret_key: str = Field(alias="secretKey")
    pending_secret_key: str | None = Field(default=None, alias="pendingSecretKey")
    is_production: bool = Field(alias="isProduction")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    deleted_at: datetime | None = Field(default=None, alias="deletedAt")


class SecretSummary(ContractModel):
    id: int
    environment_id: int = Field(alias="environmentId")
    display_name: str = Field(alias="displayName")
    secret: str
    hashed: str
    is_default: bool = Field(alias="isDefault")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class AccountContext(ContractModel):
    account: AccountSummary
    environment: EnvironmentSummary
    secret: SecretSummary
    auth_source: AuthSource = Field(alias="authSource")
    scopes: tuple[str, ...] = ()
    api_key_id: int | None = Field(default=None, alias="apiKeyId")
