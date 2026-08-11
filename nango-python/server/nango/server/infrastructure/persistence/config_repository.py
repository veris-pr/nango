from typing import Optional, List

from sqlalchemy.orm import Session

from nango.server.domain.entities import Config
from nango.server.domain.repositories import ConfigRepository as DomainConfigRepository
from nango.server.models import Config as ConfigModel


class SQLAlchemyConfigRepository(DomainConfigRepository):
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, config_id: int) -> Optional[Config]:
        model = self.session.get(ConfigModel, config_id)
        if not model:
            return None
        return self._to_entity(model)

    def get_by_provider_config_key(
        self,
        provider_config_key: str,
        environment_id: int
    ) -> Optional[Config]:
        model = self.session.query(ConfigModel).filter(
            ConfigModel.provider_config_key == provider_config_key,
            ConfigModel.environment_id == environment_id
        ).first()
        if not model:
            return None
        return self._to_entity(model)

    def get_by_environment(self, environment_id: int) -> List[Config]:
        models = self.session.query(ConfigModel).filter(
            ConfigModel.environment_id == environment_id
        ).all()
        return [self._to_entity(m) for m in models]

    def save(self, config: Config) -> Config:
        if config.id:
            model = self.session.get(ConfigModel, config.id)
            if model:
                model.provider = config.provider
                model.oauth_client_id = config.oauth_client_id
                model.oauth_client_secret = config.oauth_client_secret
                model.scopes = config.scopes
                model.custom = config.custom
                model.connection_config = config.connection_config
                model.secret = config.secret
                model.metadata = config.metadata
        else:
            model = ConfigModel(
                account_id=config.account_id,
                unique_key=config.unique_key,
                provider=config.provider,
                provider_config_key=config.provider_config_key,
                environment_id=config.environment_id,
                oauth_client_id=config.oauth_client_id,
                oauth_client_secret=config.oauth_client_secret,
                scopes=config.scopes,
                custom=config.custom,
                connection_config=config.connection_config,
                secret=config.secret,
                metadata=config.metadata,
            )
            self.session.add(model)

        self.session.commit()
        self.session.refresh(model)
        return self._to_entity(model)

    def delete(self, config_id: int) -> None:
        model = self.session.get(ConfigModel, config_id)
        if model:
            self.session.delete(model)
            self.session.commit()

    def delete_by_provider_config_key(
        self,
        provider_config_key: str,
        environment_id: int
    ) -> None:
        model = self.session.query(ConfigModel).filter(
            ConfigModel.provider_config_key == provider_config_key,
            ConfigModel.environment_id == environment_id
        ).first()
        if model:
            self.session.delete(model)
            self.session.commit()

    def _to_entity(self, model: ConfigModel) -> Config:
        return Config(
            id=model.id,
            account_id=model.account_id,
            unique_key=model.unique_key,
            provider=model.provider,
            provider_config_key=model.provider_config_key,
            environment_id=model.environment_id,
            oauth_client_id=model.oauth_client_id,
            oauth_client_secret=model.oauth_client_secret,
            scopes=model.scopes,
            custom=model.custom,
            connection_config=model.connection_config,
            secret=model.secret,
            metadata=model.metadata,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )