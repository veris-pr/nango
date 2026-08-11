from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from nango.server.database import get_db
from nango.server.models import Connection, Config, Environment

router = APIRouter()


@router.get('')
async def list_connections(
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """List all connections for an environment."""
    connections = db.query(Connection).filter(
        Connection.environment_id == environment_id
    ).all()

    return {
        'connections': [
            {
                'id': c.id,
                'connection_id': c.connection_id,
                'provider': c.provider,
                'provider_config_key': c.provider_config_key,
                'environment_id': c.environment_id,
                'created_at': c.created_at.isoformat() if c.created_at else None,
                'updated_at': c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in connections
        ]
    }


@router.get('/{connection_id}')
async def get_connection(
    connection_id: str,
    provider_config_key: str = Query(...),
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Get a specific connection."""
    connection = db.query(Connection).filter(
        Connection.connection_id == connection_id,
        Connection.environment_id == environment_id,
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail='Connection not found')

    return {
        'id': connection.id,
        'connection_id': connection.connection_id,
        'provider': connection.provider,
        'provider_config_key': connection.provider_config_key,
        'environment_id': connection.environment_id,
        'access_token': connection.access_token,
        'refresh_token': connection.refresh_token,
        'expires_at': connection.expires_at.isoformat() if connection.expires_at else None,
        'token_type': connection.token_type,
        'created_at': connection.created_at.isoformat() if connection.created_at else None,
        'updated_at': connection.updated_at.isoformat() if connection.updated_at else None,
    }


@router.delete('/{connection_id}')
async def delete_connection(
    connection_id: str,
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Delete a connection."""
    connection = db.query(Connection).filter(
        Connection.connection_id == connection_id,
        Connection.environment_id == environment_id,
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail='Connection not found')

    db.delete(connection)
    db.commit()

    return {'status': 'deleted', 'connection_id': connection_id}