import typer
import httpx
import json
from typing import Optional

app = typer.Typer(help="Nango CLI - Manage integrations and connections")


def get_base_url() -> str:
    """Get the Nango server URL from env or default."""
    import os
    return os.environ.get('NANGO_SERVER_URL', 'http://localhost:3003')


@app.command()
def init(
    name: str = typer.Argument(..., help="Integration name"),
    provider: str = typer.Option(..., '--provider', '-p', help="Provider (e.g., github, slack)"),
    client_id: str = typer.Option('', '--client-id', help="OAuth client ID"),
    client_secret: str = typer.Option('', '--client-secret', help="OAuth client secret"),
    scopes: str = typer.Option('', '--scopes', help="Comma-separated scopes"),
):
    """Create a new integration."""
    base_url = get_base_url()

    data = {
        'provider': provider,
        'provider_config_key': name,
        'oauth_client_id': client_id,
        'oauth_client_secret': client_secret,
        'scopes': scopes,
        'environment_id': 1,
    }

    response = httpx.post(f'{base_url}/api/v1/configs', data=data, timeout=30)

    if response.status_code == 200:
        typer.echo(f"✓ Integration '{name}' created successfully")
    else:
        typer.echo(f"✗ Failed to create integration: {response.text}", err=True)
        raise typer.Exit(1)


@app.command()
def list():
    """List all integrations."""
    base_url = get_base_url()

    response = httpx.get(f'{base_url}/api/v1/configs?environment_id=1', timeout=10)

    if response.status_code != 200:
        typer.echo(f"✗ Failed to fetch integrations: {response.text}", err=True)
        raise typer.Exit(1)

    configs = response.json().get('configs', [])

    if not configs:
        typer.echo("No integrations found.")
        return

    typer.echo(f"{'Provider':<20} {'Config Key':<20} {'Client ID'}")
    typer.echo("-" * 60)
    for config in configs:
        typer.echo(f"{config['provider']:<20} {config['provider_config_key']:<20} {config.get('oauth_client_id', '-')}")


@app.command()
def delete(name: str = typer.Argument(..., help="Integration name")):
    """Delete an integration."""
    base_url = get_base_url()

    response = httpx.delete(
        f'{base_url}/api/v1/configs/{name}',
        params={'environment_id': 1},
        timeout=10
    )

    if response.status_code == 200:
        typer.echo(f"✓ Integration '{name}' deleted")
    else:
        typer.echo(f"✗ Failed to delete integration: {response.text}", err=True)
        raise typer.Exit(1)


@app.command()
def auth(
    integration: str = typer.Argument(..., help="Integration name"),
    connection_id: str = typer.Option(..., '--connection-id', '-c', help="Connection ID"),
):
    """Start OAuth flow for an integration."""
    base_url = get_base_url()

    response = httpx.get(
        f'{base_url}/oauth/authorize/{integration}',
        params={
            'connection_id': connection_id,
            'environment_id': 1,
        },
        timeout=10
    )

    if response.status_code != 200:
        typer.echo(f"✗ Failed to start auth: {response.text}", err=True)
        raise typer.Exit(1)

    data = response.json()
    auth_url = data.get('authorization_url')

    if auth_url:
        typer.echo(f"✓ Open this URL in your browser:\n{auth_url}")
    else:
        typer.echo(f"✗ No authorization URL returned: {data}")


@app.command()
def connections():
    """List all connections."""
    base_url = get_base_url()

    response = httpx.get(f'{base_url}/api/v1/connections?environment_id=1', timeout=10)

    if response.status_code != 200:
        typer.echo(f"✗ Failed to fetch connections: {response.text}", err=True)
        raise typer.Exit(1)

    connections = response.json().get('connections', [])

    if not connections:
        typer.echo("No connections found.")
        return

    typer.echo(f"{'Connection ID':<30} {'Provider':<15} {'Config Key'}")
    typer.echo("-" * 70)
    for conn in connections:
        typer.echo(f"{conn['connection_id']:<30} {conn.get('provider', '-'):<15} {conn.get('provider_config_key', '-')}")


@app.command()
def get(
    connection_id: str = typer.Argument(..., help="Connection ID"),
):
    """Get connection details."""
    base_url = get_base_url()

    response = httpx.get(
        f'{base_url}/api/v1/connections/{connection_id}',
        params={'environment_id': 1},
        timeout=10
    )

    if response.status_code != 200:
        typer.echo(f"✗ Connection not found: {response.text}", err=True)
        raise typer.Exit(1)

    conn = response.json()
    typer.echo(json.dumps(conn, indent=2))


@app.command()
def delete_connection(connection_id: str = typer.Argument(..., help="Connection ID")):
    """Delete a connection."""
    base_url = get_base_url()

    response = httpx.delete(
        f'{base_url}/api/v1/connections/{connection_id}',
        params={'environment_id': 1},
        timeout=10
    )

    if response.status_code == 200:
        typer.echo(f"✓ Connection '{connection_id}' deleted")
    else:
        typer.echo(f"✗ Failed to delete connection: {response.text}", err=True)
        raise typer.Exit(1)


@app.command()
def proxy(
    method: str = typer.Argument('GET', help="HTTP method"),
    path: str = typer.Argument(..., help="API path (e.g., /user)"),
    integration: str = typer.Option(..., '--integration', '-i', help="Integration name"),
    connection_id: str = typer.Option(..., '--connection-id', '-c', help="Connection ID"),
    data: str = typer.Option('', '--data', '-d', help="Request body (JSON)"),
):
    """Make an authenticated API request through the proxy."""
    base_url = get_base_url()

    url = f'{base_url}/api/v1/proxy/{integration}/{path.lstrip("/")}'
    params = {
        'connection_id': connection_id,
        'environment_id': 1,
    }

    headers = {}
    body = None

    if data:
        headers['Content-Type'] = 'application/json'
        body = data

    try:
        response = httpx.request(
            method=method.upper(),
            url=url,
            params=params,
            headers=headers,
            content=body,
            timeout=30,
        )

        typer.echo(f"Status: {response.status_code}")

        try:
            typer.echo(json.dumps(response.json(), indent=2))
        except ValueError:
            typer.echo(response.text)

    except Exception as e:
        typer.echo(f"✗ Request failed: {str(e)}", err=True)
        raise typer.Exit(1)


if __name__ == '__main__':
    app()