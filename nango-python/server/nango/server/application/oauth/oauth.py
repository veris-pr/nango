import base64
import hashlib
import urllib.parse
from typing import Optional
from dataclasses import dataclass

import httpx

from nango.server.config import get_settings
from nango.server.domain.entities import OAuthSession, Connection
from nango.server.domain.repositories import (
    OAuthSessionRepository,
    ConfigRepository,
    ConnectionRepository,
)
from nango.server.providers import get_providers


class OAuthSessionNotFoundError(Exception):
    pass


class OAuthSessionExpiredError(Exception):
    pass


class ProviderNotFoundError(Exception):
    pass


@dataclass
class AuthorizationUrlResult:
    url: str
    state: str
    session_id: int


class AuthorizeConnection:
    def __init__(
        self,
        oauth_session_repository: OAuthSessionRepository,
        config_repository: ConfigRepository,
    ):
        self.oauth_session_repository = oauth_session_repository
        self.config_repository = config_repository

    def execute(
        self,
        provider_config_key: str,
        environment_id: int,
        connection_id: str,
        scope: str = '',
    ) -> AuthorizationUrlResult:
        config = self.config_repository.get_by_provider_config_key(
            provider_config_key, environment_id
        )
        if not config:
            raise ProviderNotFoundError(f"Provider config '{provider_config_key}' not found")

        providers = get_providers()
        provider = providers.get(provider_config_key)
        if not provider or not provider.authorization_url:
            raise ProviderNotFoundError(f"Provider '{provider_config_key}' not found")

        settings = get_settings()
        callback_base = settings.nango_server_url

        oauth_session = OAuthSession.create_oauth2(
            connection_id=connection_id,
            environment_id=environment_id,
            provider_config_key=provider_config_key,
            redirect_uri=f"{callback_base}/oauth/callback",
            scope=scope,
        )

        saved_session = self.oauth_session_repository.save(oauth_session)

        params = {
            'client_id': config.oauth_client_id or '',
            'redirect_uri': oauth_session.redirect_uri,
            'response_type': 'code',
            'scope': scope,
            'state': oauth_session.state,
        }

        if oauth_session.code_verifier:
            code_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(oauth_session.code_verifier.encode()).digest()
            ).decode().rstrip('=')
            params['code_challenge'] = code_challenge
            params['code_challenge_method'] = 'S256'

        auth_url = provider.authorization_url
        if '?' in auth_url:
            auth_url += '&'
        else:
            auth_url += '?'
        auth_url += urllib.parse.urlencode(params)

        return AuthorizationUrlResult(
            url=auth_url,
            state=oauth_session.state,
            session_id=saved_session.id,
        )


class HandleOAuthCallback:
    def __init__(
        self,
        oauth_session_repository: OAuthSessionRepository,
        config_repository: ConfigRepository,
        connection_repository: ConnectionRepository,
    ):
        self.oauth_session_repository = oauth_session_repository
        self.config_repository = config_repository
        self.connection_repository = connection_repository

    async def execute(
        self,
        code: str,
        state: str,
    ) -> dict:
        oauth_session = self.oauth_session_repository.get_by_state(state)
        if not oauth_session:
            raise OAuthSessionNotFoundError("Invalid state - session not found")

        if oauth_session.is_expired():
            raise OAuthSessionExpiredError("OAuth session expired")

        config = self.config_repository.get_by_provider_config_key(
            oauth_session.provider_config_key,
            oauth_session.environment_id,
        )
        if not config:
            raise ProviderNotFoundError("Integration config not found")

        providers = get_providers()
        provider = providers.get(oauth_session.provider_config_key)

        token_params = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': oauth_session.redirect_uri,
        }

        if oauth_session.code_verifier:
            token_params['code_verifier'] = oauth_session.code_verifier

        headers = {'Accept': 'application/json'}

        if config.oauth_client_id:
            auth_string = f"{config.oauth_client_id}:{config.oauth_client_secret or ''}"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
            headers['Authorization'] = f"Basic {auth_b64}"

        if provider and provider.token_params:
            for key, value in provider.token_params.items():
                if key not in token_params:
                    token_params[key] = value

        token_url = provider.token_url if provider else None
        if not token_url:
            raise ProviderNotFoundError("Provider does not support token exchange")

        await self._exchange_token(
            token_url, token_params, headers, config, oauth_session
        )

        self.oauth_session_repository.delete_by_state(state)

        return {
            'status': 'success',
            'connection_id': oauth_session.connection_id,
            'provider': config.provider,
        }

    async def _exchange_token(
        self,
        token_url: str,
        token_params: dict,
        headers: dict,
        config,
        oauth_session,
    ):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data=token_params,
                headers=headers,
            )

            if response.status_code != 200:
                raise Exception(f"Token exchange failed: {response.text}")

            token_data = response.json()

        access_token = token_data.get('access_token')
        if not access_token:
            raise Exception("No access_token in response")

        expires_in = token_data.get('expires_in')

        connection = Connection.create(
            connection_id=oauth_session.connection_id,
            environment_id=oauth_session.environment_id,
            config_id=config.id,
            account_id=config.account_id,
            provider=config.provider,
            provider_config_key=oauth_session.provider_config_key,
            access_token=access_token,
            refresh_token=token_data.get('refresh_token'),
            token_type=token_data.get('token_type', 'Bearer'),
            id_token=token_data.get('id_token'),
            expires_in=expires_in,
        )

        self.connection_repository.save(connection)