import httpx
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from nango.server.models import Config, Connection
from nango.server.providers import get_providers
from nango.server.services import oauth as oauth_service
from nango.server.utils import interpolate_string


class ProxyError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def refresh_token_if_needed(
    db: Session,
    connection: Connection,
    config: Config,
) -> Connection:
    """
    Check if token is expired and refresh if needed.
    """
    if connection.expires_at and connection.expires_at < datetime.utcnow():
        if not connection.refresh_token:
            raise ProxyError('Token expired and no refresh token available', 401)

        try:
            tokens = await oauth_service.refresh_access_token(
                provider_config_key=connection.provider_config_key,
                refresh_token=connection.refresh_token,
                client_id=config.oauth_client_id or '',
                client_secret=config.oauth_client_secret,
            )

            connection.access_token = tokens.access_token
            if tokens.refresh_token:
                connection.refresh_token = tokens.refresh_token
            connection.token_type = tokens.token_type
            connection.expires_at = tokens.expires_at()
            connection.last_refreshed_at = datetime.utcnow()
            db.commit()

        except ValueError as e:
            raise ProxyError(f'Token refresh failed: {str(e)}', 401)

    return connection


def build_proxy_url(
    provider_config_key: str,
    endpoint: str,
    connection: Connection,
    config: Config,
) -> str:
    """
    Build the target URL for the proxy request.
    """
    providers = get_providers()
    provider = providers.get(provider_config_key)

    if not provider or not provider.proxy or not provider.proxy.base_url:
        raise ProxyError(f'Provider {provider_config_key} does not support proxy', 400)

    base_url = provider.proxy.base_url

    # Interpolate variables
    import json
    connection_config = {}
    if connection.connection_config:
        try:
            connection_config = json.loads(connection.connection_config)
        except json.JSONDecodeError:
            pass

    credentials = {
        'apiKey': connection.api_key or '',
        'clientId': config.oauth_client_id or '',
        'clientSecret': config.oauth_client_secret or '',
    }

    # Build full URL
    if endpoint.startswith('http'):
        url = endpoint
    else:
        # Interpolate base_url
        base_url = interpolate_string(base_url, credentials, connection_config)
        url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"

    return url


def get_auth_headers(connection: Connection, config: Config) -> dict:
    """
    Build authentication headers for the proxy request.
    """
    headers = {}

    # OAuth2 / OAuth1 tokens
    if connection.access_token:
        token_type = connection.token_type or 'Bearer'
        headers['Authorization'] = f'{token_type} {connection.access_token}'

    # API Key
    if connection.api_key:
        # Get auth header config from provider
        providers = get_providers()
        provider = providers.get(config.provider)
        if provider and provider.proxy and provider.proxy.headers:
            for key, value in provider.proxy.headers.items():
                if '${apiKey}' in value:
                    headers[key] = value.replace('${apiKey}', connection.api_key)
                elif value == '${apiKey}':
                    headers[key] = connection.api_key

    # Basic auth
    if connection.basic_username and connection.basic_password:
        import base64
        auth_string = f"{connection.basic_username}:{connection.basic_password}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        headers['Authorization'] = f'Basic {auth_b64}'

    return headers


async def make_proxy_request(
    method: str,
    url: str,
    connection: Connection,
    config: Config,
    params: Optional[dict] = None,
    data: Optional[Any] = None,
    headers: Optional[dict] = None,
    timeout: int = 30,
) -> httpx.Response:
    """
    Make an authenticated request through the proxy.
    """
    auth_headers = get_auth_headers(connection, config)

    # Merge headers
    all_headers = {**auth_headers}
    if headers:
        all_headers.update(headers)

    # Remove content-type if we're sending JSON
    if data and 'Content-Type' not in all_headers:
        all_headers['Content-Type'] = 'application/json'

    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=method.upper(),
            url=url,
            params=params,
            content=data,
            headers=all_headers,
            timeout=timeout,
            follow_redirects=True,
        )

        return response