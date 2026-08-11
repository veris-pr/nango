import base64
import hashlib
import json
import secrets
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from nango.server.models import Environment, OAuthSession
from nango.server.providers import get_providers
from nango.server.utils import interpolate_string


class TokenResponse:
    """Represents an OAuth token response."""
    def __init__(
        self,
        access_token: str,
        token_type: str = 'Bearer',
        expires_in: Optional[int] = None,
        refresh_token: Optional[str] = None,
        id_token: Optional[str] = None,
        scope: Optional[str] = None,
        raw: Optional[dict] = None
    ):
        self.access_token = access_token
        self.token_type = token_type
        self.expires_in = expires_in
        self.refresh_token = refresh_token
        self.id_token = id_token
        self.scope = scope
        self.raw = raw or {}

    def expires_at(self) -> Optional[datetime]:
        if self.expires_in:
            return datetime.utcnow() + timedelta(seconds=self.expires_in)
        return None


async def exchange_code_for_tokens(
    provider_config_key: str,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: Optional[str] = None,
    code_verifier: Optional[str] = None,
    auth_method: str = 'client_secret_basic',
) -> TokenResponse:
    """
    Exchange authorization code for access token.
    """
    providers = get_providers()
    provider = providers.get(provider_config_key)

    if not provider or not provider.token_url:
        raise ValueError(f"Provider {provider_config_key} does not support token exchange")

    # Build token request
    token_params = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
    }

    if code_verifier:
        token_params['code_verifier'] = code_verifier

    headers = {
        'Accept': 'application/json',
    }

    # Handle auth method
    if auth_method == 'client_secret_basic':
        # Send client credentials in Authorization header
        auth_string = f"{client_id}:{client_secret or ''}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        headers['Authorization'] = f"Basic {auth_b64}"
    elif auth_method == 'client_secret_post':
        # Send client credentials in body
        token_params['client_id'] = client_id
        token_params['client_secret'] = client_secret or ''
    else:
        # No auth or custom
        token_params['client_id'] = client_id
        if client_secret:
            token_params['client_secret'] = client_secret

    # Add any additional token params from provider config
    if provider.token_params:
        for key, value in provider.token_params.items():
            if key not in token_params:
                token_params[key] = value

    # Make request
    async with httpx.AsyncClient() as client:
        response = await client.post(
            provider.token_url,
            data=token_params,  # application/x-www-form-urlencoded
            headers=headers,
        )

        if response.status_code != 200:
            raise ValueError(f"Token exchange failed: {response.status_code} - {response.text}")

        token_data = response.json()

    # Parse response
    access_token = token_data.get('access_token')
    if not access_token:
        raise ValueError("No access_token in response")

    # Extract token using provider's token_response mapping
    token_response_mapping = provider.token_response or {}
    actual_access_token = extract_by_path(token_data, token_response_mapping.get('token', 'access_token'))
    actual_refresh_token = extract_by_path(token_data, token_response_mapping.get('refresh_token', 'refresh_token'))
    id_token = extract_by_path(token_data, token_response_mapping.get('id_token', 'id_token'))

    # Calculate expires_in
    expires_in = provider.token_expires_in_ms
    if expires_in:
        expires_in = expires_in // 1000
    elif 'expires_in' in token_data:
        expires_in = token_data['expires_in']

    return TokenResponse(
        access_token=actual_access_token or access_token,
        token_type=token_data.get('token_type', 'Bearer'),
        expires_in=expires_in,
        refresh_token=actual_refresh_token,
        id_token=id_token,
        scope=token_data.get('scope'),
        raw=token_data,
    )


async def refresh_access_token(
    provider_config_key: str,
    refresh_token: str,
    client_id: str,
    client_secret: Optional[str] = None,
    auth_method: str = 'client_secret_basic',
) -> TokenResponse:
    """
    Refresh an access token using a refresh token.
    """
    providers = get_providers()
    provider = providers.get(provider_config_key)

    if not provider or not provider.token_url:
        raise ValueError(f"Provider {provider_config_key} does not support token refresh")

    token_params = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }

    headers = {
        'Accept': 'application/json',
    }

    if auth_method == 'client_secret_basic':
        auth_string = f"{client_id}:{client_secret or ''}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        headers['Authorization'] = f"Basic {auth_b64}"
    else:
        token_params['client_id'] = client_id
        if client_secret:
            token_params['client_secret'] = client_secret

    if provider.token_params:
        for key, value in provider.token_params.items():
            if key not in token_params:
                token_params[key] = value

    async with httpx.AsyncClient() as client:
        response = await client.post(
            provider.token_url,
            data=token_params,
            headers=headers,
        )

        if response.status_code != 200:
            raise ValueError(f"Token refresh failed: {response.status_code} - {response.text}")

        token_data = response.json()

    access_token = token_data.get('access_token')
    if not access_token:
        raise ValueError("No access_token in refresh response")

    expires_in = provider.token_expires_in_ms
    if expires_in:
        expires_in = expires_in // 1000
    elif 'expires_in' in token_data:
        expires_in = token_data['expires_in']

    # Some providers don't return a new refresh token
    new_refresh_token = token_data.get('refresh_token', refresh_token)

    return TokenResponse(
        access_token=access_token,
        token_type=token_data.get('token_type', 'Bearer'),
        expires_in=expires_in,
        refresh_token=new_refresh_token,
        id_token=token_data.get('id_token'),
        scope=token_data.get('scope'),
        raw=token_data,
    )


def extract_by_path(data: dict, path: str) -> Any:
    """Extract value from nested dict using dot notation."""
    if not path:
        return None
    keys = path.split('.')
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value





def generate_state() -> str:
    return secrets.token_urlsafe(32)


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def build_oauth2_authorization_url(
    provider_config_key: str,
    environment_id: int,
    connection_id: str,
    redirect_uri: str,
    scope: Optional[str] = None,
    state: Optional[str] = None,
    code_verifier: Optional[str] = None,
) -> tuple[str, str, Optional[str]]:
    """
    Build OAuth2 authorization URL.
    Returns: (authorization_url, state, code_verifier)
    """
    providers = get_providers()
    provider = providers.get(provider_config_key)

    if not provider:
        raise ValueError(f"Unknown provider: {provider_config_key}")

    if not provider.authorization_url:
        raise ValueError(f"Provider {provider_config_key} does not support OAuth2")

    if state is None:
        state = generate_state()

    params = {
        'client_id': '${credentials.client_id}',  # Will be interpolated
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': scope or '',
        'state': state,
    }

    # PKCE support
    code_challenge = None
    if code_verifier:
        import hashlib
        import base64
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier).digest()
        ).decode().rstrip('=')
        params['code_challenge'] = code_challenge
        params['code_challenge_method'] = 'S256'

    # Build URL
    auth_url = provider.authorization_url
    if '?' in auth_url:
        auth_url += '&'
    else:
        auth_url += '?'
    auth_url += urllib.parse.urlencode(params)

    return auth_url, state, code_verifier


def build_oauth1_authorization_url(
    provider_config_key: str,
    redirect_uri: str,
    oauth_token: str,
    oauth_token_secret: str,
) -> str:
    """
    Build OAuth1 authorization URL.
    """
    providers = get_providers()
    provider = providers.get(provider_config_key)

    if not provider:
        raise ValueError(f"Unknown provider: {provider_config_key}")

    if not provider.authorization_url:
        raise ValueError(f"Provider {provider_config_key} does not support OAuth1")

    params = {
        'oauth_token': oauth_token,
        'oauth_callback': redirect_uri,
    }

    auth_url = provider.authorization_url
    if '?' in auth_url:
        auth_url += '&'
    else:
        auth_url += '?'
    auth_url += urllib.parse.urlencode(params)

    return auth_url


def get_provider_auth_mode(provider_config_key: str) -> Optional[str]:
    """Get the auth mode for a provider."""
    providers = get_providers()
    provider = providers.get(provider_config_key)
    if not provider:
        return None
    return provider.auth_mode