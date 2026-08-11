from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class Connection:
    id: Optional[int] = None
    connection_id: str = ''
    environment_id: int = 0
    config_id: int = 0
    account_id: int = 0
    provider: Optional[str] = None
    provider_config_key: Optional[str] = None

    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    token_type: str = 'Bearer'
    id_token: Optional[str] = None

    api_key: Optional[str] = None
    basic_username: Optional[str] = None
    basic_password: Optional[str] = None

    private_key: Optional[str] = None

    connection_config: Optional[str] = None
    metadata: Optional[str] = None
    errors: Optional[str] = None

    last_refreshed_at: Optional[datetime] = None
    failed_stored_refresh: bool = False

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @staticmethod
    def create(
        connection_id: str,
        environment_id: int,
        config_id: int,
        account_id: int,
        provider: str,
        provider_config_key: str,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        token_type: str = 'Bearer',
        id_token: Optional[str] = None,
        expires_in: Optional[int] = None,
    ) -> 'Connection':
        expires_at = None
        if expires_in:
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        return Connection(
            connection_id=connection_id,
            environment_id=environment_id,
            config_id=config_id,
            account_id=account_id,
            provider=provider,
            provider_config_key=provider_config_key,
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=token_type,
            id_token=id_token,
            expires_at=expires_at,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    def is_token_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() >= self.expires_at

    def update_tokens(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
        token_type: str = 'Bearer',
        id_token: Optional[str] = None,
        expires_in: Optional[int] = None,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token or self.refresh_token
        self.token_type = token_type
        self.id_token = id_token
        if expires_in:
            self.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        self.last_refreshed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key
        self.updated_at = datetime.utcnow()

    def set_basic_auth(self, username: str, password: str) -> None:
        self.basic_username = username
        self.basic_password = password
        self.updated_at = datetime.utcnow()

    def set_private_key(self, private_key: str) -> None:
        self.private_key = private_key
        self.updated_at = datetime.utcnow()