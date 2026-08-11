from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = 'accounts'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    owner: Mapped[str] = mapped_column(String(255), nullable=True)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=True)
    uuid: Mapped[str] = mapped_column(UUID(as_uuid=False), default=lambda: str(uuid4()))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    environments: Mapped[list['Environment']] = relationship(back_populates='account')
    users: Mapped[list['User']] = relationship(back_populates='account')
    configs: Mapped[list['Config']] = relationship(back_populates='account')


class Environment(Base):
    __tablename__ = 'environments'

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    name: Mapped[str] = mapped_column(String(255))
    secret_key: Mapped[str] = mapped_column(String(255), nullable=True)
    public_key: Mapped[str] = mapped_column(String(255), nullable=True)
    secret_key_iv: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    secret_key_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    callback_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    webhooks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ssl: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    ssl_cert: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ssl_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index('idx_environment_account_id', 'account_id'),)

    account: Mapped['Account'] = relationship(back_populates='environments')
    connections: Mapped[list['Connection']] = relationship(back_populates='environment')


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reset_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reset_token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index('idx_user_account_id', 'account_id'),)

    account: Mapped['Account'] = relationship(back_populates='users')


class Config(Base):
    __tablename__ = 'configs'

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    unique_key: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(255))
    provider_config_key: Mapped[str] = mapped_column(String(255))
    environment_id: Mapped[int] = mapped_column(ForeignKey('environments.id'))
    oauth_client_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    oauth_client_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    oauth_client_secret_iv: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    oauth_client_secret_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    scopes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    custom: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    connection_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    secret_iv: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    secret_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_config_account_id', 'account_id'),
        Index('idx_config_environment_id', 'environment_id'),
        Index('idx_config_unique_key', 'unique_key'),
    )

    account: Mapped['Account'] = relationship(back_populates='configs')
    connections: Mapped[list['Connection']] = relationship(back_populates='config')


class Connection(Base):
    __tablename__ = 'connections'

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[str] = mapped_column(String(255))
    environment_id: Mapped[int] = mapped_column(ForeignKey('environments.id'))
    config_id: Mapped[int] = mapped_column(ForeignKey('configs.id'))
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'))

    provider: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_config_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # OAuth tokens
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    access_token_iv: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    access_token_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token_iv: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    refresh_token_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    token_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    id_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # API Key auth
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_key_iv: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    api_key_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Basic auth
    basic_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    basic_password: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    basic_password_iv: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    basic_password_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # App Store auth
    private_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    private_key_iv: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    private_key_tag: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Custom config
    connection_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    errors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Tracking
    last_refreshed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failed_stored_refresh: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_connection_environment_id', 'environment_id'),
        Index('idx_connection_config_id', 'config_id'),
        Index('idx_connection_account_id', 'account_id'),
        Index('idx_connection_connection_id', 'connection_id'),
    )

    environment: Mapped['Environment'] = relationship(back_populates='connections')
    config: Mapped['Config'] = relationship(back_populates='connections')


class Flow(Base):
    __tablename__ = 'flows'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    flow_type: Mapped[str] = mapped_column(String(50))  # 'sync' or 'action'
    environment_id: Mapped[int] = mapped_column(ForeignKey('environments.id'))
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    provider_config_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default='draft')  # draft, active, stopped
    runs: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # hourly, daily, etc.
    auto_start: Mapped[bool] = mapped_column(Boolean, default=False)
    track_cursors: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    input_schema: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    output_schema: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index('idx_flow_environment_id', 'environment_id'),)


class OAuthSession(Base):
    __tablename__ = 'oauth_sessions'

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[str] = mapped_column(String(255))
    environment_id: Mapped[int] = mapped_column(ForeignKey('environments.id'))
    provider_config_key: Mapped[str] = mapped_column(String(255))

    # OAuth1
    oauth_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    oauth_token_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    oauth_verifier: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # OAuth2
    state: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    code_verifier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Config
    redirect_uri: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    scope: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (
        Index('idx_oauth_sessions_state', 'state'),
        Index('idx_oauth_sessions_connection_id', 'connection_id'),
    )