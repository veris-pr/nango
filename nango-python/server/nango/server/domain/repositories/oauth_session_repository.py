from abc import ABC, abstractmethod
from typing import Optional

from nango.server.domain.entities import OAuthSession


class OAuthSessionRepository(ABC):
    @abstractmethod
    def get_by_id(self, session_id: int) -> Optional[OAuthSession]:
        pass

    @abstractmethod
    def get_by_state(self, state: str) -> Optional[OAuthSession]:
        pass

    @abstractmethod
    def save(self, session: OAuthSession) -> OAuthSession:
        pass

    @abstractmethod
    def delete(self, session_id: int) -> None:
        pass

    @abstractmethod
    def delete_by_state(self, state: str) -> None:
        pass