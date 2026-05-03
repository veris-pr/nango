# Nango Python Fork

A Python implementation of the Nango integration platform.

## Overview

This is a fork of the Nango project, rewritten in Python. It provides the same core features:
- OAuth2 authentication flows
- API proxy for authenticated requests
- 700+ pre-configured API integrations
- Admin panel for managing integrations and connections
- CLI tool for managing the platform
- Python SDK for programmatic access

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/nango-python.git

cd nango-python

# Install dependencies
pip install -e .
```

## Quick Start

```bash
# Start the server
python -m nango.server.main

# Open http://localhost:3003 in your browser
```

## CLI Usage

```bash
# Initialize a new integration
nango-cli init my-github --provider github --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET

# List integrations
nango-cli list

# Start OAuth flow
nango-cli auth github --connection-id user-123

# Make an API request
nango-cli proxy GET /user --integration github --connection-id user-123
```

## Python SDK Usage

```python
from nango import Nango

# Initialize client
nango = Nango(secret_key='nango_sk_...')

# Make API request
response = nango.get('/user', provider_config_key='github', connection_id='user-123')
print(response.json())
```

## Features

### OAuth Flow
- Initiate OAuth2 authorization
- Handle callback and exchange code for tokens
- Auto-refresh expired tokens

### API Proxy
- Make authenticated requests to external APIs
- Supports GET, POST, PUT, DELETE, PATCH
- Injects stored credentials automatically

### Admin Panel
- Web interface for managing integrations and connections
- Create, view, and delete integrations
- View connection details

### CLI Tool
- Command-line interface for managing the platform
- Initialize integrations
- Start OAuth flows
- Make API requests

### Python SDK
- Library for programmatic access to Nango
- Easy integration with Python applications

## Database Setup

The project uses PostgreSQL. Create a database named `nango` and update your `.env` file with the connection details.

## Environment Variables

Create a `.env` file in the project root with the following variables:

```env
NANGO_ENCRYPTION_KEY=your-encryption-key
NANGO_DB_URL=postgresql://nango:nango@localhost:5432/nango
SERVER_PORT=3003
NANGO_SERVER_URL=http://localhost:3003
NANGO_PUBLIC_SERVER_URL=http://localhost:3000
```

## Development

```bash
# Run tests
pytest tests/

# Run linter
ruff check .
```

## License

This project is licensed under the Elastic License 2.0. See [LICENSE](LICENSE) for details.