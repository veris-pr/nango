from abc import ABC, abstractmethod
from typing import Optional, List

from nango.server.domain.entities import Connection


class ConnectionRepository(ABC):
    @abstractmethod
    def get_by_id(self, connection_id: int) -> Optional[Connection]:
        pass

    @abstractmethod
    def get_by_connection_id(
        self,
        connection_id: str,
        environment_id: int
    ) -> Optional[Connection]:
        pass

    @abstractmethod
    def get_by_environment(self, environment_id: int) -> List[Connection]:
        pass

    @abstractmethod
    def save(self, connection: Connection) -> Connection:
        pass

    @abstractmethod
    def delete(self, connection_id: int) -> None:
        pass

    @abstractmethod
    def delete_by_connection_id(
        self,
        connection_id: str,
        environment_id: int
    ) -> None:
        pass