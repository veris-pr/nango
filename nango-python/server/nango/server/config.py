from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = Field(
        default='postgresql://nango:nango@localhost:5432/nango',
        alias='NANGO_DB_URL'
    )

    # Redis
    redis_url: str = Field(
        default='redis://localhost:6379',
        alias='REDIS_URL'
    )

    # Server
    server_port: int = Field(default=3003, alias='SERVER_PORT')
    server_host: str = Field(default='0.0.0.0', alias='SERVER_HOST')

    # Auth
    encryption_key: str = Field(alias='NANGO_ENCRYPTION_KEY')
    nango_server_url: str = Field(
        default='http://localhost:3003',
        alias='NANGO_SERVER_URL'
    )
    nango_public_server_url: str = Field(
        default='http://localhost:3000',
        alias='NANGO_PUBLIC_SERVER_URL'
    )

    # Dashboard
    dashboard_username: Optional[str] = Field(default=None, alias='NANGO_DASHBOARD_USERNAME')
    dashboard_password: Optional[str] = Field(default=None, alias='NANGO_DASHBOARD_PASSWORD')

    # Logs
    logs_enabled: bool = Field(default=False, alias='NANGO_LOGS_ENABLED')
    logs_es_url: str = Field(
        default='http://localhost:9200',
        alias='NANGO_LOGS_ES_URL'
    )

    class Config:
        env_file = '.env'
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()