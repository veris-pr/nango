from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from nango.server.database import get_db
from nango.server.transport.schemas.config import (
    ConfigResponse,
    ConfigListResponse,
    DeleteConfigResponse,
)
from nango.server.infrastructure.persistence import (
    SQLAlchemyConfigRepository,
    SQLAlchemyEnvironmentRepository,
    SQLAlchemyAccountRepository,
)
from nango.server.application.config import (
    GetConfig,
    ListConfigs,
    CreateConfig,
    DeleteConfig,
    ConfigNotFoundError,
    ConfigAlreadyExistsError,
)


class ConfigUseCases:
    def __init__(self, session: Session):
        config_repo = SQLAlchemyConfigRepository(session)
        env_repo = SQLAlchemyEnvironmentRepository(session)
        account_repo = SQLAlchemyAccountRepository(session)
        self.get = GetConfig(config_repository=config_repo)
        self.list = ListConfigs(config_repository=config_repo)
        self.create = CreateConfig(
            config_repository=config_repo,
            environment_repository=env_repo,
            account_repository=account_repo,
        )
        self.delete = DeleteConfig(config_repository=config_repo)


def get_config_use_cases(session: Session) -> ConfigUseCases:
    return ConfigUseCases(session)


def list_configs(
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    use_cases = get_config_use_cases(db)
    configs = use_cases.list.execute(environment_id)

    return ConfigListResponse(
        configs=[
            ConfigResponse(
                id=c.id,
                provider=c.provider,
                provider_config_key=c.provider_config_key,
                oauth_client_id=c.oauth_client_id,
                scopes=c.scopes,
                created_at=c.created_at.isoformat() if c.created_at else None,
                updated_at=c.updated_at.isoformat() if c.updated_at else None,
            )
            for c in configs
        ]
    )


def get_config(
    provider_config_key: str,
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    use_cases = get_config_use_cases(db)
    try:
        config = use_cases.get.execute(provider_config_key, environment_id)
        return ConfigResponse(
            id=config.id,
            provider=config.provider,
            provider_config_key=config.provider_config_key,
            oauth_client_id=config.oauth_client_id,
            scopes=config.scopes,
            created_at=config.created_at.isoformat() if config.created_at else None,
            updated_at=config.updated_at.isoformat() if config.updated_at else None,
        )
    except ConfigNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


def create_config(
    provider: str,
    provider_config_key: str,
    environment_id: int,
    oauth_client_id: str = '',
    oauth_client_secret: str = '',
    scopes: str = '',
    db: Session = Depends(get_db)
):
    use_cases = get_config_use_cases(db)
    try:
        config = use_cases.create.execute(
            provider=provider,
            provider_config_key=provider_config_key,
            environment_id=environment_id,
            oauth_client_id=oauth_client_id or None,
            oauth_client_secret=oauth_client_secret or None,
            scopes=scopes or None,
        )
        return ConfigResponse(
            id=config.id,
            provider=config.provider,
            provider_config_key=config.provider_config_key,
            oauth_client_id=config.oauth_client_id,
            scopes=config.scopes,
            created_at=config.created_at.isoformat() if config.created_at else None,
            updated_at=config.updated_at.isoformat() if config.updated_at else None,
        )
    except ConfigAlreadyExistsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConfigNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


def delete_config(
    provider_config_key: str,
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    use_cases = get_config_use_cases(db)
    try:
        use_cases.delete.execute(provider_config_key, environment_id)
        return DeleteConfigResponse(
            status='deleted',
            provider_config_key=provider_config_key
        )
    except ConfigNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))