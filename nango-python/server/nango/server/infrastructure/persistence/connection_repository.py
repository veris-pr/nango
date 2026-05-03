from typing import Optional, List

from sqlalchemy.orm import Session

from nango.server.domain.entities import Connection
from nango.server.domain.repositories import ConnectionRepository as DomainConnectionRepository
from nango.server.models import Connection as ConnectionModel


class SQLAlchemyConnectionRepository(DomainConnectionRepository):
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, connection_id: int) -> Optional[Connection]:
        model = self.session.get(ConnectionModel, connection_id)
        if not model:
            return None
        return self._to_entity(model)

    def get_by_connection_id(
        self,
        connection_id: str,
        environment_id: int
    ) -> Optional[Connection]:
        model = self.session.query(ConnectionModel).filter(
            ConnectionModel.connection_id == connection_id,
            ConnectionModel.environment_id == environment_id
        ).first()
        if not model:
            return None
        return self._to_entity(model)

    def get_by_environment(self, environment_id: int) -> List[Connection]:
        models = self.session.query(ConnectionModel).filter(
            ConnectionModel.environment_id == environment_id
        ).all()
        return [self._to_entity(m) for m in models]

    def save(self, connection: Connection) -> Connection:
        if connection.id:
            model = self.session.get(ConnectionModel, connection.id)
            if model:
                self._update_model(model, connection)
        else:
            model = ConnectionModel(
                connection_id=connection.connection_id,
                environment_id=connection.environment_id,
                config_id=connection.config_id,
                account_id=connection.account_id,
                provider=connection.provider,
                provider_config_key=connection.provider_config_key,
                access_token=connection.access_token,
                refresh_token=connection.refresh_token,
                expires_at=connection.expires_at,
                token_type=connection.token_type,
                id_token=connection.id_token,
                api_key=connection.api_key,
                basic_username=connection.basic_username,
                basic_password=connection.basic_password,
                private_key=connection.private_key,
                connection_config=connection.connection_config,
                metadata=connection.metadata,
                errors=connection.errors,
            )
            self.session.add(model)

        self.session.commit()
        self.session.refresh(model)
        return self._to_entity(model)

    def delete(self, connection_id: int) -> None:
        model = self.session.get(ConnectionModel, connection_id)
        if model:
            self.session.delete(model)
            self.session.commit()

    def delete_by_connection_id(
        self,
        connection_id: str,
        environment_id: int
    ) -> None:
        model = self.session.query(ConnectionModel).filter(
            ConnectionModel.connection_id == connection_id,
            ConnectionModel.environment_id == environment_id
        ).first()
        if model:
            self.session.delete(model)
            self.session.commit()

    def _update_model(self, model: ConnectionModel, connection: Connection) -> None:
        model.provider = connection.provider
        model.provider_config_key = connection.provider_config_key
        model.access_token = connection.access_token
        model.refresh_token = connection.refresh_token
        model.expires_at = connection.expires_at
        model.token_type = connection.token_type
        model.id_token = connection.id_token
        model.api_key = connection.api_key
        model.basic_username = connection.basic_username
        model.basic_password = connection.basic_password
        model.private_key = connection.private_key
        model.connection_config = connection.connection_config
        model.metadata = connection.metadata
        model.errors = connection.errors
        model.last_refreshed_at = connection.last_refreshed_at
        model.failed_stored_refresh = connection.failed_stored_refresh

    def _to_entity(self, model: ConnectionModel) -> Connection:
        return Connection(
            id=model.id,
            connection_id=model.connection_id,
            environment_id=model.environment_id,
            config_id=model.config_id,
            account_id=model.account_id,
            provider=model.provider,
            provider_config_key=model.provider_config_key,
            access_token=model.access_token,
            refresh_token=model.refresh_token,
            expires_at=model.expires_at,
            token_type=model.token_type,
            id_token=model.id_token,
            api_key=model.api_key,
            basic_username=model.basic_username,
            basic_password=model.basic_password,
            private_key=model.private_key,
            connection_config=model.connection_config,
            metadata=model.metadata,
            errors=model.errors,
            last_refreshed_at=model.last_refreshed_at,
            failed_stored_refresh=model.failed_stored_refresh,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )