from typing import Optional
from pydantic import BaseModel, Field


class CreateConfigRequest(BaseModel):
    provider: str = Field(..., description="Provider name (e.g., github, slack)")
    provider_config_key: str = Field(..., description="Unique config key")
    oauth_client_id: Optional[str] = Field(None, description="OAuth client ID")
    oauth_client_secret: Optional[str] = Field(None, description="OAuth client secret")
    scopes: Optional[str] = Field(None, description="Comma-separated scopes")


class ConfigResponse(BaseModel):
    id: int
    provider: str
    provider_config_key: str
    oauth_client_id: Optional[str]
    scopes: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


class ConfigListResponse(BaseModel):
    configs: list[ConfigResponse]


class DeleteConfigResponse(BaseModel):
    status: str
    provider_config_key: str