from functools import lru_cache
from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from nango.server.database import get_db
from nango.server.transport.schemas.oauth import AuthorizeResponse, OAuthCallbackResponse
from nango.server.infrastructure.persistence import (
    SQLAlchemyOAuthSessionRepository,
    SQLAlchemyConfigRepository,
    SQLAlchemyConnectionRepository,
)
from nango.server.application.oauth import (
    AuthorizeConnection,
    HandleOAuthCallback,
    OAuthSessionNotFoundError,
    OAuthSessionExpiredError,
    ProviderNotFoundError,
)


class OAuthUseCases:
    def __init__(self, session: Session):
        self.authorize = AuthorizeConnection(
            oauth_session_repository=SQLAlchemyOAuthSessionRepository(session),
            config_repository=SQLAlchemyConfigRepository(session),
        )
        self.callback = HandleOAuthCallback(
            oauth_session_repository=SQLAlchemyOAuthSessionRepository(session),
            config_repository=SQLAlchemyConfigRepository(session),
            connection_repository=SQLAlchemyConnectionRepository(session),
        )


def get_oauth_use_cases(session: Session) -> OAuthUseCases:
    return OAuthUseCases(session)


def authorize(
    provider_config_key: str,
    connection_id: str = Query(...),
    environment_id: int = Query(...),
    scope: str = Query(''),
    db: Session = Depends(get_db)
):
    use_cases = get_oauth_use_cases(db)
    try:
        result = use_cases.authorize.execute(
            provider_config_key=provider_config_key,
            environment_id=environment_id,
            connection_id=connection_id,
            scope=scope,
        )
        return AuthorizeResponse(
            authorization_url=result.url,
            state=result.state,
            session_id=result.session_id,
        )
    except ProviderNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))


async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str = Query(None),
    db: Session = Depends(get_db)
):
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    use_cases = get_oauth_use_cases(db)
    try:
        result = await use_cases.callback.execute(code=code, state=state)
        return OAuthCallbackResponse(
            status=result.status,
            connection_id=result.connection_id,
            provider=result.provider,
        )
    except OAuthSessionNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OAuthSessionExpiredError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ProviderNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))