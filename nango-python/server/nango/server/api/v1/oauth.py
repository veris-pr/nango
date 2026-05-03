from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from nango.server.database import get_db
from nango.server.models import Config, Connection, Environment, OAuthSession
from nango.server.services import oauth as oauth_service

router = APIRouter()


@router.get('/authorize/{provider_config_key}')
async def oauth_authorize(
    provider_config_key: str,
    connection_id: str = Query(...),
    environment_id: int = Query(...),
    scope: str = Query(default=''),
    db: Session = Depends(get_db)
):
    """
    Initiate OAuth2 flow - returns authorization URL.
    """
    # Get config
    config = db.query(Config).filter(
        Config.provider_config_key == provider_config_key,
        Config.environment_id == environment_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail='Integration not found')

    # Get environment for callback URL
    environment = db.query(Environment).filter(
        Environment.id == environment_id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail='Environment not found')

    callback_base = environment.callback_url or 'http://localhost:3003'
    redirect_uri = f"{callback_base}/oauth/callback"

    # Get provider to check auth mode
    auth_mode = oauth_service.get_provider_auth_mode(provider_config_key)

    if auth_mode == 'OAUTH2':
        try:
            import json
            credentials = {}
            if config.oauth_client_id:
                credentials['client_id'] = config.oauth_client_id

            connection_config = {}
            if config.connection_config:
                try:
                    connection_config = json.loads(config.connection_config)
                except json.JSONDecodeError:
                    pass

            # Build authorization URL
            auth_url, state, code_verifier = oauth_service.build_oauth2_authorization_url(
                provider_config_key=provider_config_key,
                environment_id=environment_id,
                connection_id=connection_id,
                redirect_uri=redirect_uri,
                scope=scope,
            )

            # Interpolate the URL with credentials
            auth_url = oauth_service.interpolate_string(
                auth_url, credentials, connection_config
            )

            # Store OAuth session for validation
            oauth_session = OAuthSession(
                connection_id=connection_id,
                environment_id=environment_id,
                provider_config_key=provider_config_key,
                state=state,
                code_verifier=code_verifier,
                redirect_uri=redirect_uri,
                scope=scope,
            )
            db.add(oauth_session)
            db.commit()

            return {'authorization_url': auth_url, 'state': state, 'session_id': oauth_session.id}

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    elif auth_mode in ('OAUTH2_CC', 'OAUTH2_CLIENT_CREDENTIALS'):
        raise HTTPException(status_code=400, detail='Use /token endpoint for client credentials flow')

    else:
        raise HTTPException(status_code=400, detail=f'Unsupported auth mode: {auth_mode}')


@router.get('/callback')
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str = Query(default=None),
    db: Session = Depends(get_db)
):
    """
    Handle OAuth2 callback - exchange code for tokens and create connection.
    """
    if error:
        raise HTTPException(status_code=400, detail=f'OAuth error: {error}')

    # Find the OAuth session by state
    oauth_session = db.query(OAuthSession).filter(
        OAuthSession.state == state
    ).first()

    if not oauth_session:
        raise HTTPException(status_code=400, detail='Invalid state - session not found')

    # Check if expired
    if oauth_session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail='OAuth session expired')

    # Get config
    config = db.query(Config).filter(
        Config.provider_config_key == oauth_session.provider_config_key,
        Config.environment_id == oauth_session.environment_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail='Integration config not found')

    try:
        # Exchange code for tokens
        tokens = await oauth_service.exchange_code_for_tokens(
            provider_config_key=oauth_session.provider_config_key,
            code=code,
            redirect_uri=oauth_session.redirect_uri,
            client_id=config.oauth_client_id or '',
            client_secret=config.oauth_client_secret,
            code_verifier=oauth_session.code_verifier,
            auth_method='client_secret_basic',
        )

        # Create or update connection
        connection = db.query(Connection).filter(
            Connection.connection_id == oauth_session.connection_id,
            Connection.environment_id == oauth_session.environment_id
        ).first()

        if connection:
            # Update existing connection
            connection.access_token = tokens.access_token
            connection.refresh_token = tokens.refresh_token
            connection.token_type = tokens.token_type
            connection.expires_at = tokens.expires_at()
            connection.id_token = tokens.id_token
        else:
            # Create new connection
            connection = Connection(
                connection_id=oauth_session.connection_id,
                environment_id=oauth_session.environment_id,
                config_id=config.id,
                account_id=config.account_id,
                provider=config.provider,
                provider_config_key=oauth_session.provider_config_key,
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                token_type=tokens.token_type,
                expires_at=tokens.expires_at(),
                id_token=tokens.id_token,
            )
            db.add(connection)

        # Clean up OAuth session
        db.delete(oauth_session)
        db.commit()

        return {
            'status': 'success',
            'connection_id': oauth_session.connection_id,
            'provider': config.provider,
            'expires_at': tokens.expires_at().isoformat() if tokens.expires_at() else None,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/token')
async def oauth_token(
    grant_type: str = Query(...),
    client_id: str = Query(...),
    client_secret: str = Query(None),
    code: str = Query(default=None),
    redirect_uri: str = Query(default=None),
    refresh_token: str = Query(default=None),
    environment_id: int = Query(default=1),
    provider_config_key: str = Query(default=None),
    connection_id: str = Query(default=None),
    db: Session = Depends(get_db)
):
    """
    Exchange authorization code or refresh token for tokens.
    """
    if grant_type == 'authorization_code':
        if not code or not redirect_uri:
            raise HTTPException(status_code=400, detail='code and redirect_uri required')

        if not provider_config_key or not connection_id:
            raise HTTPException(status_code=400, detail='provider_config_key and connection_id required')

        config = db.query(Config).filter(
            Config.provider_config_key == provider_config_key,
            Config.environment_id == environment_id
        ).first()

        if not config:
            raise HTTPException(status_code=404, detail='Integration not found')

        try:
            tokens = await oauth_service.exchange_code_for_tokens(
                provider_config_key=provider_config_key,
                code=code,
                redirect_uri=redirect_uri,
                client_id=config.oauth_client_id or client_id,
                client_secret=config.oauth_client_secret or client_secret,
            )

            # Create connection
            connection = Connection(
                connection_id=connection_id,
                environment_id=environment_id,
                config_id=config.id,
                account_id=config.account_id,
                provider=config.provider,
                provider_config_key=provider_config_key,
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                token_type=tokens.token_type,
                expires_at=tokens.expires_at(),
                id_token=tokens.id_token,
            )
            db.add(connection)
            db.commit()

            return {
                'access_token': tokens.access_token,
                'token_type': tokens.token_type,
                'expires_in': tokens.expires_in,
                'refresh_token': tokens.refresh_token,
                'id_token': tokens.id_token,
            }

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    elif grant_type == 'refresh_token':
        if not refresh_token:
            raise HTTPException(status_code=400, detail='refresh_token required')

        if not connection_id or not provider_config_key:
            raise HTTPException(status_code=400, detail='connection_id and provider_config_key required')

        connection = db.query(Connection).filter(
            Connection.connection_id == connection_id,
            Connection.environment_id == environment_id
        ).first()

        if not connection:
            raise HTTPException(status_code=404, detail='Connection not found')

        config = db.query(Config).filter(
            Config.provider_config_key == provider_config_key,
            Config.environment_id == environment_id
        ).first()

        if not config:
            raise HTTPException(status_code=404, detail='Integration not found')

        try:
            tokens = await oauth_service.refresh_access_token(
                provider_config_key=provider_config_key,
                refresh_token=refresh_token,
                client_id=config.oauth_client_id or client_id,
                client_secret=config.oauth_client_secret or client_secret,
            )

            # Update connection
            connection.access_token = tokens.access_token
            if tokens.refresh_token:
                connection.refresh_token = tokens.refresh_token
            connection.token_type = tokens.token_type
            connection.expires_at = tokens.expires_at()
            connection.last_refreshed_at = datetime.utcnow()
            db.commit()

            return {
                'access_token': tokens.access_token,
                'token_type': tokens.token_type,
                'expires_in': tokens.expires_in,
                'refresh_token': tokens.refresh_token,
            }

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    else:
        raise HTTPException(status_code=400, detail=f'Unsupported grant_type: {grant_type}')