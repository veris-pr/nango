from typing import Optional
from pydantic import BaseModel, Field


class CreateConnectionRequest(BaseModel):
    provider_config_key: str = Field(..., description="Provider config key")
    connection_id: str = Field(..., description="Connection ID")
    access_token: str = Field(..., description="Access token")
    refresh_token: Optional[str] = Field(None, description="Refresh token")
    token_type: str = Field("Bearer", description="Token type")
    id_token: Optional[str] = Field(None, description="ID token")
    expires_in: Optional[int] = Field(None, description="Expires in seconds")


class ConnectionResponse(BaseModel):
    id: int
    connection_id: str
    provider: Optional[str]
    provider_config_key: Optional[str]
    environment_id: int
    created_at: Optional[str]
    updated_at: Optional[str]


class ConnectionListResponse(BaseModel):
    connections: list[ConnectionResponse]


class DeleteConnectionResponse(BaseModel):
    status: str
    connection_id: str