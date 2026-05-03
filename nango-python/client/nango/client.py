"""
Nango Python Client
====================
A Python SDK for interacting with the Nango integration platform.

Usage:
    from nango import Nango

    nango = Nango(secret_key='nango_sk_...')

    # Get connection
    connection = nango.get_connection('github', 'user-123')

    # Make API request
    response = nango.get('/user', provider_config_key='github', connection_id='user-123')
"""

import httpx
from typing import Any, Optional


class NangoError(Exception):
    """Base exception for Nango errors."""
    pass


class Nango:
    """
    Python client for Nango integration platform.
    """

    def __init__(
        self,
        secret_key: str,
        base_url: str = 'http://localhost:3003',
        timeout: int = 30,
    ):
        """
        Initialize the Nango client.

        Args:
            secret_key: Your Nango secret key
            base_url: Base URL of your Nango server (default: http://localhost:3003)
            timeout: Request timeout in seconds (default: 30)
        """
        self.secret_key = secret_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def _headers(self, additional: Optional[dict] = None) -> dict:
        """Build request headers."""
        headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
        }
        if additional:
            headers.update(additional)
        return headers

    # Connection Management

    def get_connection(self, connection_id: str, provider_config_key: str, environment_id: int = 1) -> dict:
        """
        Get connection details.

        Args:
            connection_id: The connection ID
            provider_config_key: The integration provider config key
            environment_id: The environment ID (default: 1)

        Returns:
            Connection details including credentials
        """
        response = self._client.get(
            f'{self.base_url}/api/v1/connections/{connection_id}',
            params={'environment_id': environment_id, 'provider_config_key': provider_config_key},
            headers=self._headers(),
        )

        if response.status_code == 404:
            raise NangoError(f"Connection '{connection_id}' not found")
        elif response.status_code != 200:
            raise NangoError(f"Failed to get connection: {response.text}")

        return response.json()

    def list_connections(self, environment_id: int = 1) -> list:
        """List all connections."""
        response = self._client.get(
            f'{self.base_url}/api/v1/connections',
            params={'environment_id': environment_id},
            headers=self._headers(),
        )

        if response.status_code != 200:
            raise NangoError(f"Failed to list connections: {response.text}")

        return response.json().get('connections', [])

    def delete_connection(self, connection_id: str, environment_id: int = 1) -> bool:
        """Delete a connection."""
        response = self._client.delete(
            f'{self.base_url}/api/v1/connections/{connection_id}',
            params={'environment_id': environment_id},
            headers=self._headers(),
        )

        if response.status_code != 200:
            raise NangoError(f"Failed to delete connection: {response.text}")

        return True

    # Integration Management

    def list_integrations(self, environment_id: int = 1) -> list:
        """List all integrations."""
        response = self._client.get(
            f'{self.base_url}/api/v1/configs',
            params={'environment_id': environment_id},
            headers=self._headers(),
        )

        if response.status_code != 200:
            raise NangoError(f"Failed to list integrations: {response.text}")

        return response.json().get('configs', [])

    def get_integration(self, provider_config_key: str, environment_id: int = 1) -> dict:
        """Get integration details."""
        integrations = self.list_integrations(environment_id)

        for i in integrations:
            if i['provider_config_key'] == provider_config_key:
                return i

        raise NangoError(f"Integration '{provider_config_key}' not found")

    def create_integration(
        self,
        provider: str,
        provider_config_key: str,
        environment_id: int = 1,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        scopes: Optional[str] = None,
    ) -> dict:
        """Create a new integration."""
        data = {
            'provider': provider,
            'provider_config_key': provider_config_key,
            'environment_id': environment_id,
        }

        if oauth_client_id:
            data['oauth_client_id'] = oauth_client_id
        if oauth_client_secret:
            data['oauth_client_secret'] = oauth_client_secret
        if scopes:
            data['scopes'] = scopes

        response = self._client.post(
            f'{self.base_url}/api/v1/configs',
            data=data,
            headers=self._headers(),
        )

        if response.status_code == 400 and 'already exists' in response.text:
            raise NangoError(f"Integration '{provider_config_key}' already exists")
        elif response.status_code != 200:
            raise NangoError(f"Failed to create integration: {response.text}")

        return response.json()

    def delete_integration(self, provider_config_key: str, environment_id: int = 1) -> bool:
        """Delete an integration."""
        response = self._client.delete(
            f'{self.base_url}/api/v1/configs/{provider_config_key}',
            params={'environment_id': environment_id},
            headers=self._headers(),
        )

        if response.status_code != 200:
            raise NangoError(f"Failed to delete integration: {response.text}")

        return True

    # OAuth

    def get_authorization_url(
        self,
        provider_config_key: str,
        connection_id: str,
        environment_id: int = 1,
        scope: str = '',
    ) -> str:
        """
        Get OAuth authorization URL for a connection.

        Args:
            provider_config_key: The integration provider config key
            connection_id: The connection ID to create
            environment_id: The environment ID (default: 1)
            scope: OAuth scopes (comma-separated)

        Returns:
            Authorization URL to redirect the user to
        """
        response = self._client.get(
            f'{self.base_url}/oauth/authorize/{provider_config_key}',
            params={
                'connection_id': connection_id,
                'environment_id': environment_id,
                'scope': scope,
            },
            headers=self._headers(),
        )

        if response.status_code != 200:
            raise NangoError(f"Failed to get authorization URL: {response.text}")

        data = response.json()
        return data.get('authorization_url', '')

    # Proxy - make authenticated API requests

    def request(
        self,
        method: str,
        endpoint: str,
        provider_config_key: str,
        connection_id: str,
        environment_id: int = 1,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> httpx.Response:
        """
        Make an authenticated request through the Nango proxy.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            endpoint: API endpoint path (e.g., '/user' or 'user')
            provider_config_key: The integration provider config key
            connection_id: The connection ID to use
            environment_id: The environment ID (default: 1)
            params: Query parameters
            data: Request body (will be JSON encoded)
            headers: Additional headers

        Returns:
            httpx.Response object
        """
        url = f'{self.base_url}/api/v1/proxy/{provider_config_key}/{endpoint.lstrip("/")}'

        request_params = {
            'connection_id': connection_id,
            'environment_id': environment_id,
        }
        if params:
            request_params.update(params)

        request_headers = self._headers(headers)

        response = self._client.request(
            method=method.upper(),
            url=url,
            params=request_params,
            headers=request_headers,
            json=data if data else None,
        )

        return response

    def get(self, endpoint: str, provider_config_key: str, connection_id: str, **kwargs) -> httpx.Response:
        """GET request through proxy."""
        return self.request('GET', endpoint, provider_config_key, connection_id, **kwargs)

    def post(self, endpoint: str, provider_config_key: str, connection_id: str, **kwargs) -> httpx.Response:
        """POST request through proxy."""
        return self.request('POST', endpoint, provider_config_key, connection_id, **kwargs)

    def put(self, endpoint: str, provider_config_key: str, connection_id: str, **kwargs) -> httpx.Response:
        """PUT request through proxy."""
        return self.request('PUT', endpoint, provider_config_key, connection_id, **kwargs)

    def delete(self, endpoint: str, provider_config_key: str, connection_id: str, **kwargs) -> httpx.Response:
        """DELETE request through proxy."""
        return self.request('DELETE', endpoint, provider_config_key, connection_id, **kwargs)

    def patch(self, endpoint: str, provider_config_key: str, connection_id: str, **kwargs) -> httpx.Response:
        """PATCH request through proxy."""
        return self.request('PATCH', endpoint, provider_config_key, connection_id, **kwargs)

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class NangoAsync:
    """
    Async Python client for Nango integration platform.
    """

    def __init__(
        self,
        secret_key: str,
        base_url: str = 'http://localhost:3003',
        timeout: int = 30,
    ):
        self.secret_key = secret_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _headers(self, additional: Optional[dict] = None) -> dict:
        headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
        }
        if additional:
            headers.update(additional)
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def get_connection(self, connection_id: str, provider_config_key: str, environment_id: int = 1) -> dict:
        client = await self._get_client()
        response = await client.get(
            f'{self.base_url}/api/v1/connections/{connection_id}',
            params={'environment_id': environment_id, 'provider_config_key': provider_config_key},
            headers=self._headers(),
        )

        if response.status_code == 404:
            raise NangoError(f"Connection '{connection_id}' not found")
        elif response.status_code != 200:
            raise NangoError(f"Failed to get connection: {response.text}")

        return response.json()

    async def list_connections(self, environment_id: int = 1) -> list:
        client = await self._get_client()
        response = await client.get(
            f'{self.base_url}/api/v1/connections',
            params={'environment_id': environment_id},
            headers=self._headers(),
        )

        if response.status_code != 200:
            raise NangoError(f"Failed to list connections: {response.text}")

        return response.json().get('connections', [])

    async def delete_connection(self, connection_id: str, environment_id: int = 1) -> bool:
        client = await self._get_client()
        response = await client.delete(
            f'{self.base_url}/api/v1/connections/{connection_id}',
            params={'environment_id': environment_id},
            headers=self._headers(),
        )

        if response.status_code != 200:
            raise NangoError(f"Failed to delete connection: {response.text}")

        return True

    async def list_integrations(self, environment_id: int = 1) -> list:
        client = await self._get_client()
        response = await client.get(
            f'{self.base_url}/api/v1/configs',
            params={'environment_id': environment_id},
            headers=self._headers(),
        )

        if response.status_code != 200:
            raise NangoError(f"Failed to list integrations: {response.text}")

        return response.json().get('configs', [])

    async def get_integration(self, provider_config_key: str, environment_id: int = 1) -> dict:
        integrations = await self.list_integrations(environment_id)

        for i in integrations:
            if i['provider_config_key'] == provider_config_key:
                return i

        raise NangoError(f"Integration '{provider_config_key}' not found")

    async def create_integration(
        self,
        provider: str,
        provider_config_key: str,
        environment_id: int = 1,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        scopes: Optional[str] = None,
    ) -> dict:
        data = {
            'provider': provider,
            'provider_config_key': provider_config_key,
            'environment_id': environment_id,
        }

        if oauth_client_id:
            data['oauth_client_id'] = oauth_client_id
        if oauth_client_secret:
            data['oauth_client_secret'] = oauth_client_secret
        if scopes:
            data['scopes'] = scopes

        client = await self._get_client()
        response = await client.post(
            f'{self.base_url}/api/v1/configs',
            data=data,
            headers=self._headers(),
        )

        if response.status_code == 400 and 'already exists' in response.text:
            raise NangoError(f"Integration '{provider_config_key}' already exists")
        elif response.status_code != 200:
            raise NangoError(f"Failed to create integration: {response.text}")

        return response.json()

    async def delete_integration(self, provider_config_key: str, environment_id: int = 1) -> bool:
        client = await self._get_client()
        response = await client.delete(
            f'{self.base_url}/api/v1/configs/{provider_config_key}',
            params={'environment_id': environment_id},
            headers=self._headers(),
        )

        if response.status_code != 200:
            raise NangoError(f"Failed to delete integration: {response.text}")

        return True

    async def get_authorization_url(
        self,
        provider_config_key: str,
        connection_id: str,
        environment_id: int = 1,
        scope: str = '',
    ) -> str:
        client = await self._get_client()
        response = await client.get(
            f'{self.base_url}/oauth/authorize/{provider_config_key}',
            params={
                'connection_id': connection_id,
                'environment_id': environment_id,
                'scope': scope,
            },
            headers=self._headers(),
        )

        if response.status_code != 200:
            raise NangoError(f"Failed to get authorization URL: {response.text}")

        data = response.json()
        return data.get('authorization_url', '')

    async def request(
        self,
        method: str,
        endpoint: str,
        provider_config_key: str,
        connection_id: str,
        environment_id: int = 1,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> httpx.Response:
        url = f'{self.base_url}/api/v1/proxy/{provider_config_key}/{endpoint.lstrip("/")}'

        request_params = {
            'connection_id': connection_id,
            'environment_id': environment_id,
        }
        if params:
            request_params.update(params)

        request_headers = self._headers(headers)

        client = await self._get_client()
        response = await client.request(
            method=method.upper(),
            url=url,
            params=request_params,
            headers=request_headers,
            json=data if data else None,
        )

        return response

    async def get(self, endpoint: str, provider_config_key: str, connection_id: str, **kwargs) -> httpx.Response:
        return await self.request('GET', endpoint, provider_config_key, connection_id, **kwargs)

    async def post(self, endpoint: str, provider_config_key: str, connection_id: str, **kwargs) -> httpx.Response:
        return await self.request('POST', endpoint, provider_config_key, connection_id, **kwargs)

    async def put(self, endpoint: str, provider_config_key: str, connection_id: str, **kwargs) -> httpx.Response:
        return await self.request('PUT', endpoint, provider_config_key, connection_id, **kwargs)

    async def delete(self, endpoint: str, provider_config_key: str, connection_id: str, **kwargs) -> httpx.Response:
        return await self.request('DELETE', endpoint, provider_config_key, connection_id, **kwargs)

    async def patch(self, endpoint: str, provider_config_key: str, connection_id: str, **kwargs) -> httpx.Response:
        return await self.request('PATCH', endpoint, provider_config_key, connection_id, **kwargs)

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()