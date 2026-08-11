from typing import Optional, List
from dataclasses import dataclass

from nango.server.domain.entities import Connection
from nango.server.domain.repositories import ConnectionRepository, ConfigRepository


class ConnectionNotFoundError(Exception):
    pass


class ConfigNotFoundError(Exception):
    pass


@dataclass
class ConnectionDTO:
    id: int
    connection_id: str
    provider: Optional[str]
    provider_config_key: Optional[str]
    environment_id: int
    created_at: Optional[str]
    updated_at: Optional[str]


class GetConnection:
    def __init__(
        self,
        connection_repository: ConnectionRepository,
    ):
        self.connection_repository = connection_repository

    def execute(
        self,
        connection_id: str,
        environment_id: int,
    ) -> Connection:
        connection = self.connection_repository.get_by_connection_id(
            connection_id, environment_id
        )
        if not connection:
            raise ConnectionNotFoundError(f"Connection '{connection_id}' not found")
        return connection


class ListConnections:
    def __init__(
        self,
        connection_repository: ConnectionRepository,
    ):
        self.connection_repository = connection_repository

    def execute(self, environment_id: int) -> List[Connection]:
        return self.connection_repository.get_by_environment(environment_id)


class CreateConnection:
    def __init__(
        self,
        connection_repository: ConnectionRepository,
        config_repository: ConfigRepository,
    ):
        self.connection_repository = connection_repository
        self.config_repository = config_repository

    def execute(
        self,
        connection_id: str,
        environment_id: int,
        provider_config_key: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        token_type: str = 'Bearer',
        id_token: Optional[str] = None,
        expires_in: Optional[int] = None,
    ) -> Connection:
        config = self.config_repository.get_by_provider_config_key(
            provider_config_key, environment_id
        )
        if not config:
            raise ConfigNotFoundError(f"Config '{provider_config_key}' not found")

        connection = Connection.create(
            connection_id=connection_id,
            environment_id=environment_id,
            config_id=config.id,
            account_id=config.account_id,
            provider=config.provider,
            provider_config_key=provider_config_key,
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=token_type,
            id_token=id_token,
            expires_in=expires_in,
        )

        return self.connection_repository.save(connection)


class DeleteConnection:
    def __init__(
        self,
        connection_repository: ConnectionRepository,
    ):
        self.connection_repository = connection_repository

    def execute(
        self,
        connection_id: str,
        environment_id: int,
    ) -> None:
        self.connection_repository.delete_by_connection_id(
            connection_id, environment_id
        )


class RefreshConnectionToken:
    def __init__(
        self,
        connection_repository: ConnectionRepository,
    ):
        self.connection_repository = connection_repository

    def execute(
        self,
        connection_id: str,
        environment_id: int,
        access_token: str,
        refresh_token: Optional[str] = None,
        token_type: str = 'Bearer',
        expires_in: Optional[int] = None,
    ) -> Connection:
        connection = self.connection_repository.get_by_connection_id(
            connection_id, environment_id
        )
        if not connection:
            raise ConnectionNotFoundError(f"Connection '{connection_id}' not found")

        connection.update_tokens(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=token_type,
            expires_in=expires_in,
        )

        return self.connection_repository.save(connection)