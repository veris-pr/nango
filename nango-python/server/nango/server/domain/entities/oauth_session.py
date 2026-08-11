from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
import secrets


@dataclass
class OAuthSession:
    id: Optional[int] = None
    connection_id: str = ''
    environment_id: int = 0
    provider_config_key: str = ''

    oauth_token: Optional[str] = None
    oauth_token_secret: Optional[str] = None
    oauth_verifier: Optional[str] = None

    state: Optional[str] = None
    code_verifier: Optional[str] = None

    redirect_uri: Optional[str] = None
    scope: Optional[str] = None

    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    @staticmethod
    def create_oauth1(
        connection_id: str,
        environment_id: int,
        provider_config_key: str,
        oauth_token: str,
        oauth_token_secret: str,
        redirect_uri: str,
    ) -> 'OAuthSession':
        state = secrets.token_urlsafe(32)
        return OAuthSession(
            connection_id=connection_id,
            environment_id=environment_id,
            provider_config_key=provider_config_key,
            oauth_token=oauth_token,
            oauth_token_secret=oauth_token_secret,
            state=state,
            redirect_uri=redirect_uri,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=10)
        )

    @staticmethod
    def create_oauth2(
        connection_id: str,
        environment_id: int,
        provider_config_key: str,
        redirect_uri: str,
        scope: Optional[str] = None,
    ) -> 'OAuthSession':
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        return OAuthSession(
            connection_id=connection_id,
            environment_id=environment_id,
            provider_config_key=provider_config_key,
            state=state,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
            scope=scope,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=10)
        )

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return True
        return datetime.utcnow() >= self.expires_at