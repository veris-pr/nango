from abc import ABC, abstractmethod
from typing import Optional, List

from nango.server.domain.entities import Config


class ConfigRepository(ABC):
    @abstractmethod
    def get_by_id(self, config_id: int) -> Optional[Config]:
        pass

    @abstractmethod
    def get_by_provider_config_key(
        self,
        provider_config_key: str,
        environment_id: int
    ) -> Optional[Config]:
        pass

    @abstractmethod
    def get_by_environment(self, environment_id: int) -> List[Config]:
        pass

    @abstractmethod
    def save(self, config: Config) -> Config:
        pass

    @abstractmethod
    def delete(self, config_id: int) -> None:
        pass

    @abstractmethod
    def delete_by_provider_config_key(
        self,
        provider_config_key: str,
        environment_id: int
    ) -> None:
        pass