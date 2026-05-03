from typing import Optional
from pydantic import BaseModel, Field


class AuthorizeRequest(BaseModel):
    provider_config_key: str = Field(..., description="Provider config key")
    connection_id: str = Field(..., description="Connection ID to create")
    scope: str = Field("", description="OAuth scopes")


class AuthorizeResponse(BaseModel):
    authorization_url: str
    state: str
    session_id: int


class OAuthCallbackRequest(BaseModel):
    code: str = Field(..., description="Authorization code")
    state: str = Field(..., description="State parameter")
    error: Optional[str] = Field(None, description="OAuth error if any")


class OAuthCallbackResponse(BaseModel):
    status: str
    connection_id: str
    provider: str


class TokenRequest(BaseModel):
    grant_type: str = Field(..., description="Grant type (authorization_code or refresh_token)")
    code: Optional[str] = Field(None, description="Authorization code")
    refresh_token: Optional[str] = Field(None, description="Refresh token")
    redirect_uri: Optional[str] = Field(None, description="Redirect URI")
    client_id: Optional[str] = Field(None, description="Client ID")
    client_secret: Optional[str] = Field(None, description="Client secret")
    provider_config_key: Optional[str] = Field(None, description="Provider config key")
    connection_id: Optional[str] = Field(None, description="Connection ID")
    environment_id: int = Field(1, description="Environment ID")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: Optional[int]
    refresh_token: Optional[str]
    id_token: Optional[str]