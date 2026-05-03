from typing import Optional

from sqlalchemy.orm import Session

from nango.server.domain.entities import OAuthSession
from nango.server.domain.repositories import OAuthSessionRepository as DomainOAuthSessionRepository
from nango.server.models import OAuthSession as OAuthSessionModel


class SQLAlchemyOAuthSessionRepository(DomainOAuthSessionRepository):
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, session_id: int) -> Optional[OAuthSession]:
        model = self.session.get(OAuthSessionModel, session_id)
        if not model:
            return None
        return self._to_entity(model)

    def get_by_state(self, state: str) -> Optional[OAuthSession]:
        model = self.session.query(OAuthSessionModel).filter(
            OAuthSessionModel.state == state
        ).first()
        if not model:
            return None
        return self._to_entity(model)

    def save(self, session: OAuthSession) -> OAuthSession:
        if session.id:
            model = self.session.get(OAuthSessionModel, session.id)
            if model:
                model.connection_id = session.connection_id
                model.environment_id = session.environment_id
                model.provider_config_key = session.provider_config_key
                model.oauth_token = session.oauth_token
                model.oauth_token_secret = session.oauth_token_secret
                model.oauth_verifier = session.oauth_verifier
                model.state = session.state
                model.code_verifier = session.code_verifier
                model.redirect_uri = session.redirect_uri
                model.scope = session.scope
                model.expires_at = session.expires_at
        else:
            model = OAuthSessionModel(
                connection_id=session.connection_id,
                environment_id=session.environment_id,
                provider_config_key=session.provider_config_key,
                oauth_token=session.oauth_token,
                oauth_token_secret=session.oauth_token_secret,
                oauth_verifier=session.oauth_verifier,
                state=session.state,
                code_verifier=session.code_verifier,
                redirect_uri=session.redirect_uri,
                scope=session.scope,
                created_at=session.created_at,
                expires_at=session.expires_at,
            )
            self.session.add(model)

        self.session.commit()
        self.session.refresh(model)
        return self._to_entity(model)

    def delete(self, session_id: int) -> None:
        model = self.session.get(OAuthSessionModel, session_id)
        if model:
            self.session.delete(model)
            self.session.commit()

    def delete_by_state(self, state: str) -> None:
        model = self.session.query(OAuthSessionModel).filter(
            OAuthSessionModel.state == state
        ).first()
        if model:
            self.session.delete(model)
            self.session.commit()

    def _to_entity(self, model: OAuthSessionModel) -> OAuthSession:
        return OAuthSession(
            id=model.id,
            connection_id=model.connection_id,
            environment_id=model.environment_id,
            provider_config_key=model.provider_config_key,
            oauth_token=model.oauth_token,
            oauth_token_secret=model.oauth_token_secret,
            oauth_verifier=model.oauth_verifier,
            state=model.state,
            code_verifier=model.code_verifier,
            redirect_uri=model.redirect_uri,
            scope=model.scope,
            created_at=model.created_at,
            expires_at=model.expires_at,
        )