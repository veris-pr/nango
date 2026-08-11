from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from nango.server.database import get_db
from nango.server.models import Config, Connection
from nango.server.services.proxy import (
    ProxyError,
    build_proxy_url,
    make_proxy_request,
    refresh_token_if_needed,
)

router = APIRouter()


def get_connection(
    connection_id: str,
    provider_config_key: str,
    environment_id: int,
    db: Session,
) -> tuple[Connection, Config]:
    """Get connection and config, or raise 404."""
    config = db.query(Config).filter(
        Config.provider_config_key == provider_config_key,
        Config.environment_id == environment_id,
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail='Integration not found')

    connection = db.query(Connection).filter(
        Connection.connection_id == connection_id,
        Connection.environment_id == environment_id,
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail='Connection not found')

    return connection, config


@router.api_route('/proxy/{provider_config_key}/{path:path}', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
async def proxy_request(
    provider_config_key: str,
    path: str,
    connection_id: str = Query(...),
    environment_id: int = Query(...),
    method: str = Query(default=None),  # Override HTTP method
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Proxy an authenticated request to an external API.
    """
    try:
        connection, config = get_connection(connection_id, provider_config_key, environment_id, db)

        # Refresh token if needed
        connection = await refresh_token_if_needed(db, connection, config)

        # Build the target URL
        endpoint = f"/{path}"
        if request.query_params:
            # Pass through query params
            endpoint += '?' + str(request.query_params)

        url = build_proxy_url(provider_config_key, endpoint, connection, config)

        # Get request body if present
        body = None
        if request and method in ('POST', 'PUT', 'PATCH'):
            body = await request.body()

        # Determine HTTP method
        http_method = method or request.method if request else 'GET'

        # Make the proxy request
        response = await make_proxy_request(
            method=http_method,
            url=url,
            connection=connection,
            config=config,
            data=body,
        )

        # Return the response
        content_type = response.headers.get('content-type', '')

        if 'application/json' in content_type:
            try:
                return JSONResponse(content=response.json(), status_code=response.status_code)
            except ValueError:
                return JSONResponse(content={'data': response.text}, status_code=response.status_code)

        elif 'text/event-stream' in content_type or 'stream' in content_type:
            return StreamingResponse(
                response.aiter_bytes(),
                status_code=response.status_code,
                media_type=content_type,
            )

        else:
            return StreamingResponse(
                response.aiter_bytes(),
                status_code=response.status_code,
                media_type=content_type,
            )

    except ProxyError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Proxy error: {str(e)}')


@router.get('/proxy/{provider_config_key}/{path:path}')
async def proxy_get(
    provider_config_key: str,
    path: str,
    connection_id: str = Query(...),
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Proxy GET requests."""
    return await proxy_request(provider_config_key, path, connection_id, environment_id, 'GET', None, db)


@router.post('/proxy/{provider_config_key}/{path:path}')
async def proxy_post(
    provider_config_key: str,
    path: str,
    connection_id: str = Query(...),
    environment_id: int = Query(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Proxy POST requests."""
    return await proxy_request(provider_config_key, path, connection_id, environment_id, 'POST', request, db)


@router.put('/proxy/{provider_config_key}/{path:path}')
async def proxy_put(
    provider_config_key: str,
    path: str,
    connection_id: str = Query(...),
    environment_id: int = Query(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Proxy PUT requests."""
    return await proxy_request(provider_config_key, path, connection_id, environment_id, 'PUT', request, db)


@router.delete('/proxy/{provider_config_key}/{path:path}')
async def proxy_delete(
    provider_config_key: str,
    path: str,
    connection_id: str = Query(...),
    environment_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Proxy DELETE requests."""
    return await proxy_request(provider_config_key, path, connection_id, environment_id, 'DELETE', None, db)