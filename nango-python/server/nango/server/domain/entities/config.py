from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class Config:
    id: Optional[int] = None
    account_id: int = 0
    unique_key: str = ''
    provider: str = ''
    provider_config_key: str = ''
    environment_id: int = 0
    oauth_client_id: Optional[str] = None
    oauth_client_secret: Optional[str] = None
    scopes: Optional[str] = None
    custom: Optional[str] = None
    connection_config: Optional[str] = None
    secret: Optional[str] = None
    metadata: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @staticmethod
    def create(
        account_id: int,
        environment_id: int,
        provider: str,
        provider_config_key: str,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        scopes: Optional[str] = None,
    ) -> 'Config':
        return Config(
            account_id=account_id,
            environment_id=environment_id,
            provider=provider,
            provider_config_key=provider_config_key,
            unique_key=provider_config_key,
            oauth_client_id=oauth_client_id,
            oauth_client_secret=oauth_client_secret,
            scopes=scopes,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    def update_tokens(
        self,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        scopes: Optional[str] = None,
    ) -> None:
        if oauth_client_id is not None:
            self.oauth_client_id = oauth_client_id
        if oauth_client_secret is not None:
            self.oauth_client_secret = oauth_client_secret
        if scopes is not None:
            self.scopes = scopes
        self.updated_at = datetime.utcnow()