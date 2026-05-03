from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from nango.server.database import get_db
from nango.server.transport.schemas.connection import (
    ConnectionResponse,
    ConnectionListResponse,
    DeleteConnectionResponse,
)
from nango.server.infrastructure.persistence import (
    SQLAlchemyConnectionRepository,
    SQLAlchemyConfigRepository,
)
from nango.server.application.connection import (
    GetConnection,
    ListConnections,
    CreateConnection,
    DeleteConnection,
    ConnectionNotFoundError,
    ConfigNotFoundError,
)


class ConnectionUseCases:
    def __init__(self, session: Session):
        connection_repo = SQLAlchemyConnectionRepository(session)
        config_repo = SQLAlchemyConfigRepository(session)
        self.get = GetConnection(connection_repository=connection_repo)
        self.list = ListConnections(connection_repository=connection_repo)
        self.create = CreateConnection(
            connection_repository=connection_repo,
            config_repository=config_repo,
        )
        self.delete = DeleteConnection(connection_repository=connection_repo)


def get_connection_use_cases(session: Session) -> ConnectionUseCases:
    return ConnectionUseCases(session)


def list_connections(
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    use_cases = get_connection_use_cases(db)
    connections = use_cases.list.execute(environment_id)

    return ConnectionListResponse(
        connections=[
            ConnectionResponse(
                id=c.id,
                connection_id=c.connection_id,
                provider=c.provider,
                provider_config_key=c.provider_config_key,
                environment_id=c.environment_id,
                created_at=c.created_at.isoformat() if c.created_at else None,
                updated_at=c.updated_at.isoformat() if c.updated_at else None,
            )
            for c in connections
        ]
    )


def get_connection(
    connection_id: str,
    provider_config_key: str = Query(...),
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    use_cases = get_connection_use_cases(db)
    try:
        connection = use_cases.get.execute(connection_id, environment_id)
        return ConnectionResponse(
            id=connection.id,
            connection_id=connection.connection_id,
            provider=connection.provider,
            provider_config_key=connection.provider_config_key,
            environment_id=connection.environment_id,
            created_at=connection.created_at.isoformat() if connection.created_at else None,
            updated_at=connection.updated_at.isoformat() if connection.updated_at else None,
        )
    except ConnectionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


def delete_connection(
    connection_id: str,
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    use_cases = get_connection_use_cases(db)
    try:
        use_cases.delete.execute(connection_id, environment_id)
        return DeleteConnectionResponse(
            status='deleted',
            connection_id=connection_id
        )
    except ConnectionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))