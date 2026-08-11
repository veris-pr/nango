from abc import ABC, abstractmethod
from typing import Optional, List

from nango.server.domain.entities import Account, Environment


class AccountRepository(ABC):
    @abstractmethod
    def get_by_id(self, account_id: int) -> Optional[Account]:
        pass

    @abstractmethod
    def get_by_uuid(self, uuid: str) -> Optional[Account]:
        pass

    @abstractmethod
    def save(self, account: Account) -> Account:
        pass

    @abstractmethod
    def delete(self, account_id: int) -> None:
        pass


class EnvironmentRepository(ABC):
    @abstractmethod
    def get_by_id(self, environment_id: int) -> Optional[Environment]:
        pass

    @abstractmethod
    def get_by_account_id(self, account_id: int) -> List[Environment]:
        pass

    @abstractmethod
    def save(self, environment: Environment) -> Environment:
        pass

    @abstractmethod
    def delete(self, environment_id: int) -> None:
        pass

    @abstractmethod
    def get_default(self, account_id: int) -> Optional[Environment]:
        pass