# How-to: Add a new API endpoint

> **Task:** Add a new endpoint end-to-end, from domain to test.

This guide walks through adding `GET /connections/:connectionId/usage` — a
hypothetical endpoint that returns usage stats for a connection. It touches
all four DDD layers.

## Before you start

1. **Read the TypeScript source of truth.** Does this endpoint exist in
   TypeScript? If yes, port it. If no, design it TypeScript-first.
2. **Identify the bounded context.** Connection usage belongs in `connections`.
3. **Read the existing pattern.** Look at `GetConnection` in
   `connections/application/get_connection.py` for the established pattern.

## Step 1 — Domain layer

Define the data shape and errors:

```python
# src/nango_py/connections/domain/usage.py

from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ConnectionUsage:
    connection_id: str
    provider_config_key: str
    record_count: int
    last_sync_at: str | None
```

```python
# src/nango_py/connections/domain/errors.py (add to existing)

class UsageNotAvailable(ApiError):
    status = 404
    code = "usage_not_available"
    message = "Usage data not available for this connection"
```

## Step 2 — Application layer

Define the gateway Protocol (how to fetch usage):

```python
# src/nango_py/connections/application/gateway.py (add to existing)

class UsageRepository(Protocol):
    async def get_usage(
        self, *, environment_id: int, connection_id: str,
        provider_config_key: str,
    ) -> ConnectionUsage | None: ...
```

Write the use case:

```python
# src/nango_py/connections/application/get_usage.py

from __future__ import annotations
from dataclasses import dataclass
from nango_py.auth.domain.context import AuthenticatedContext
from nango_py.connections.domain.usage import ConnectionUsage
from nango_py.connections.domain.errors import UsageNotAvailable

USAGE_READ_SCOPE = "environment:connections:read"

@dataclass(frozen=True)
class GetUsageRequest:
    connection_id: str
    provider_config_key: str
    context: AuthenticatedContext

class GetConnectionUsage:
    def __init__(self, *, usage_repository: UsageRepository):
        self._repo = usage_repository

    async def execute(self, request: GetUsageRequest) -> ConnectionUsage:
        if not request.context.scopes.has(USAGE_READ_SCOPE):
            raise Forbidden((USAGE_READ_SCOPE,))

        usage = await self._repo.get_usage(
            environment_id=request.context.environment.id,
            connection_id=request.connection_id,
            provider_config_key=request.provider_config_key,
        )
        if usage is None:
            raise UsageNotAvailable()
        return usage
```

## Step 3 — Infrastructure layer

Implement the repository:

```python
# src/nango_py/connections/infrastructure/sqlalchemy_usage_repository.py

class SqlAlchemyUsageRepository:
    def __init__(self, session_factory):
        self._sf = session_factory

    async def get_usage(self, *, environment_id, connection_id,
                        provider_config_key) -> ConnectionUsage | None:
        async with self._sf() as session:
            row = (
                await session.execute(
                    text("""
                        SELECT connection_id, provider_config_key,
                               record_count, last_sync_at
                        FROM connection_usage
                        WHERE environment_id = :eid
                          AND connection_id = :cid
                          AND provider_config_key = :pck
                    """),
                    {"eid": environment_id, "cid": connection_id,
                     "pck": provider_config_key},
                )
            ).mappings().first()
        if row is None:
            return None
        return ConnectionUsage(**dict(row))
```

## Step 4 — Transport layer

Add the route:

```python
# src/nango_py/connections/transport/routes.py (add to existing router)

@router.get("/connections/{connection_id}/usage")
async def get_connection_usage_route(
    connection_id: str,
    auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    provider_config_key: str = Query(..., alias="provider_config_key"),
) -> JSONResponse:
    usage = await get_usage.execute(
        GetUsageRequest(
            connection_id=connection_id,
            provider_config_key=provider_config_key,
            context=auth,
        )
    )
    return JSONResponse({
        "connectionId": usage.connection_id,
        "providerConfigKey": usage.provider_config_key,
        "recordCount": usage.record_count,
        "lastSyncAt": usage.last_sync_at,
    })
```

## Step 5 — Wire into the composition root

In `server/app.py`:

```python
from nango_py.connections.application.get_usage import (
    GetConnectionUsage, GetUsageRequest,
)
from nango_py.connections.infrastructure.sqlalchemy_usage_repository import (
    SqlAlchemyUsageRepository,
)

# In create_app():
usage_repo = SqlAlchemyUsageRepository(session_factory)
get_usage = GetConnectionUsage(usage_repository=usage_repo)

# Pass get_usage to create_connections_router
app.include_router(
    create_connections_router(
        list_connections, get_connection, connection_crud, get_usage
    )
)
```

## Step 6 — Write tests

```python
# tests/integration/test_connections_route.py (add to existing)

async def test_get_connection_usage(client, auth_headers, seed_connection):
    response = await client.get(
        f"/connections/test-conn/usage?provider_config_key=google",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["connectionId"] == "test-conn"
    assert "recordCount" in body
```

## Step 7 — Run the gates

```bash
uv run ruff check .
uv run mypy
uv run pytest tests/integration/test_connections_route.py -v
```

## Checklist

- [ ] Read TypeScript source (source of truth)
- [ ] Domain: dataclass + typed error
- [ ] Application: Protocol + use case with scope check
- [ ] Infrastructure: SQLAlchemy repository
- [ ] Transport: route with validation + serialization
- [ ] Wired into `server/app.py`
- [ ] Integration test against real Postgres
- [ ] ruff, mypy, pytest all green
- [ ] Response shape matches TypeScript (if porting)