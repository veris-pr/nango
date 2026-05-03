from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from nango.server.database import get_db
from nango.server.models import Connection, Config, Environment

router = APIRouter()


# Connection endpoints
@router.get('/connections')
async def list_connections(
    environment_id: int,
    db: Session = Depends(get_db)
):
    connections = db.query(Connection).filter(
        Connection.environment_id == environment_id
    ).all()
    return {'connections': [c.connection_id for c in connections]}


@router.get('/connections/{connection_id}')
async def get_connection(
    connection_id: str,
    environment_id: int,
    db: Session = Depends(get_db)
):
    connection = db.query(Connection).filter(
        Connection.connection_id == connection_id,
        Connection.environment_id == environment_id
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail='Connection not found')

    return {
        'id': connection.id,
        'connection_id': connection.connection_id,
        'provider': connection.provider,
        'created_at': connection.created_at.isoformat() if connection.created_at else None,
    }


@router.delete('/connections/{connection_id}')
async def delete_connection(
    connection_id: str,
    environment_id: int,
    db: Session = Depends(get_db)
):
    connection = db.query(Connection).filter(
        Connection.connection_id == connection_id,
        Connection.environment_id == environment_id
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail='Connection not found')

    db.delete(connection)
    db.commit()

    return {'deleted': True}


# Config endpoints
@router.get('/configs')
async def list_configs(
    environment_id: int,
    db: Session = Depends(get_db)
):
    configs = db.query(Config).filter(
        Config.environment_id == environment_id
    ).all()

    return {
        'configs': [
            {
                'provider': c.provider,
                'provider_config_key': c.provider_config_key,
            }
            for c in configs
        ]
    }


@router.post('/configs')
async def create_config(
    provider: str,
    provider_config_key: str,
    environment_id: int,
    db: Session = Depends(get_db)
):
    config = db.query(Config).filter(
        Config.environment_id == environment_id,
        Config.provider_config_key == provider_config_key
    ).first()

    if config:
        raise HTTPException(status_code=400, detail='Config already exists')

    account = db.query(Environment).filter(
        Environment.id == environment_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail='Environment not found')

    config = Config(
        provider=provider,
        provider_config_key=provider_config_key,
        environment_id=environment_id,
        account_id=account.account_id,
        unique_key=f'{provider_config_key}',
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    return {'id': config.id}


@router.delete('/configs/{provider_config_key}')
async def delete_config(
    provider_config_key: str,
    environment_id: int,
    db: Session = Depends(get_db)
):
    config = db.query(Config).filter(
        Config.provider_config_key == provider_config_key,
        Config.environment_id == environment_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail='Config not found')

    db.delete(config)
    db.commit()

    return {'deleted': True}


# Environment endpoints
@router.get('/environments')
async def list_environments(
    account_id: int,
    db: Session = Depends(get_db)
):
    environments = db.query(Environment).filter(
        Environment.account_id == account_id
    ).all()

    return {
        'environments': [
            {
                'id': e.id,
                'name': e.name,
                'created_at': e.created_at.isoformat() if e.created_at else None,
            }
            for e in environments
        ]
    }


@router.get('/environments/{environment_id}')
async def get_environment(
    environment_id: int,
    db: Session = Depends(get_db)
):
    env = db.query(Environment).filter(
        Environment.id == environment_id
    ).first()

    if not env:
        raise HTTPException(status_code=404, detail='Environment not found')

    return {
        'id': env.id,
        'name': env.name,
        'account_id': env.account_id,
    }