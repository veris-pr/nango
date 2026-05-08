from datetime import datetime
from typing import Any

from pydantic import model_validator

from nango.contracts.base import ContractModel


class EndUserInput(ContractModel):
    id: str
    email: str | None = None
    display_name: str | None = None
    tags: dict[str, str] | None = None


class OrganizationInput(ContractModel):
    id: str
    display_name: str | None = None


class IntegrationConfigDefaults(ContractModel):
    user_scopes: str | None = None
    authorization_params: dict[str, str] | None = None
    connection_config: dict[str, Any] | None = None


class ConnectSessionCreateRequest(ContractModel):
    allowed_integrations: list[str] | None = None
    integrations_config_defaults: dict[str, IntegrationConfigDefaults] | None = None
    end_user: EndUserInput | None = None
    organization: OrganizationInput | None = None
    tags: dict[str, str] | None = None
    overrides: dict[str, dict[str, str | None]] | None = None

    @model_validator(mode="after")
    def require_end_user_or_tags(self) -> "ConnectSessionCreateRequest":
        if self.end_user is None and self.tags is None:
            raise ValueError("connect session requests require end_user or tags")
        return self


class ConnectSessionToken(ContractModel):
    token: str
    connect_link: str
    expires_at: datetime


class ConnectSessionCreateResponse(ContractModel):
    data: ConnectSessionToken
