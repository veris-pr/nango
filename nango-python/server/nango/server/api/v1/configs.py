from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from nango.server.database import get_db
from nango.server.models import Config, Environment

router = APIRouter()


@router.get('')
async def list_configs(
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """List all integration configs for an environment."""
    configs = db.query(Config).filter(
        Config.environment_id == environment_id
    ).all()

    return {
        'configs': [
            {
                'id': c.id,
                'provider': c.provider,
                'provider_config_key': c.provider_config_key,
                'oauth_client_id': c.oauth_client_id,
                'scopes': c.scopes,
                'created_at': c.created_at.isoformat() if c.created_at else None,
                'updated_at': c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in configs
        ]
    }


@router.get('/{provider_config_key}')
async def get_config(
    provider_config_key: str,
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Get a specific integration config."""
    config = db.query(Config).filter(
        Config.provider_config_key == provider_config_key,
        Config.environment_id == environment_id,
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail='Integration not found')

    return {
        'id': config.id,
        'provider': config.provider,
        'provider_config_key': config.provider_config_key,
        'oauth_client_id': config.oauth_client_id,
        'scopes': config.scopes,
        'connection_config': config.connection_config,
        'metadata': config.metadata,
        'created_at': config.created_at.isoformat() if config.created_at else None,
        'updated_at': config.updated_at.isoformat() if config.updated_at else None,
    }


@router.post('')
async def create_config(
    provider: str = Query(...),
    provider_config_key: str = Query(...),
    environment_id: int = Query(...),
    oauth_client_id: str = Query(default=''),
    oauth_client_secret: str = Query(default=''),
    scopes: str = Query(default=''),
    account_id: int = Query(default=1),
    db: Session = Depends(get_db)
):
    """Create a new integration config."""
    existing = db.query(Config).filter(
        Config.provider_config_key == provider_config_key,
        Config.environment_id == environment_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail=f"Integration '{provider_config_key}' already exists")

    config = Config(
        provider=provider,
        provider_config_key=provider_config_key,
        environment_id=environment_id,
        account_id=account_id,
        unique_key=provider_config_key,
        oauth_client_id=oauth_client_id or None,
        oauth_client_secret=oauth_client_secret or None,
        scopes=scopes or None,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    return {
        'id': config.id,
        'provider': config.provider,
        'provider_config_key': config.provider_config_key,
        'oauth_client_id': config.oauth_client_id,
        'scopes': config.scopes,
        'created_at': config.created_at.isoformat() if config.created_at else None,
    }


@router.delete('/{provider_config_key}')
async def delete_config(
    provider_config_key: str,
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Delete an integration config."""
    config = db.query(Config).filter(
        Config.provider_config_key == provider_config_key,
        Config.environment_id == environment_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail='Integration not found')

    db.delete(config)
    db.commit()

    return {'status': 'deleted', 'provider_config_key': provider_config_key}