from typing import Optional, List
from dataclasses import dataclass

from nango.server.domain.entities import Config
from nango.server.domain.repositories import ConfigRepository, EnvironmentRepository, AccountRepository


class ConfigNotFoundError(Exception):
    pass


class ConfigAlreadyExistsError(Exception):
    pass


class CreateConfig:
    def __init__(
        self,
        config_repository: ConfigRepository,
        environment_repository: EnvironmentRepository,
        account_repository: AccountRepository,
    ):
        self.config_repository = config_repository
        self.environment_repository = environment_repository
        self.account_repository = account_repository

    def execute(
        self,
        provider: str,
        provider_config_key: str,
        environment_id: int,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        scopes: Optional[str] = None,
    ) -> Config:
        existing = self.config_repository.get_by_provider_config_key(
            provider_config_key, environment_id
        )
        if existing:
            raise ConfigAlreadyExistsError(
                f"Config '{provider_config_key}' already exists"
            )

        environment = self.environment_repository.get_by_id(environment_id)
        if not environment:
            raise ConfigNotFoundError(f"Environment '{environment_id}' not found")

        config = Config.create(
            account_id=environment.account_id,
            environment_id=environment_id,
            provider=provider,
            provider_config_key=provider_config_key,
            oauth_client_id=oauth_client_id,
            oauth_client_secret=oauth_client_secret,
            scopes=scopes,
        )

        return self.config_repository.save(config)


class GetConfig:
    def __init__(
        self,
        config_repository: ConfigRepository,
    ):
        self.config_repository = config_repository

    def execute(
        self,
        provider_config_key: str,
        environment_id: int,
    ) -> Config:
        config = self.config_repository.get_by_provider_config_key(
            provider_config_key, environment_id
        )
        if not config:
            raise ConfigNotFoundError(f"Config '{provider_config_key}' not found")
        return config


class ListConfigs:
    def __init__(
        self,
        config_repository: ConfigRepository,
    ):
        self.config_repository = config_repository

    def execute(self, environment_id: int) -> List[Config]:
        return self.config_repository.get_by_environment(environment_id)


class DeleteConfig:
    def __init__(
        self,
        config_repository: ConfigRepository,
    ):
        self.config_repository = config_repository

    def execute(
        self,
        provider_config_key: str,
        environment_id: int,
    ) -> None:
        self.config_repository.delete_by_provider_config_key(
            provider_config_key, environment_id
        )