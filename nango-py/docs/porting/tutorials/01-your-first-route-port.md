# Tutorial: Your first route port

> **Goal:** Port a TypeScript API route to Python and get it passing against
> real migrated Postgres. By the end you'll have a working endpoint that
> matches the TypeScript contract.

This tutorial walks through porting a representative read endpoint. We'll use
`GET /providers/:provider` as the example because it exercises auth,
validation, provider catalog lookup, and response serialization — the four
concerns every route port touches.

## Prerequisites

- `nango-py/` bootstrapped (`uv sync --extra dev`)
- Docker running (testcontainers needs it for Postgres)
- Read [the architecture rules](../../dev/docs/PythonCoreImplementationPlan.md#architecture-rules)

## Step 1 — Read the TypeScript controller

Start in the TypeScript source of truth. For `GET /providers/:provider`:

```
packages/server/lib/controllers/providers/getProvider.ts
```

Extract the contract:
- **Path:** `GET /providers/:provider`
- **Auth:** `connectSessionOrApiAuth` (bearer token or connect session)
- **Query:** `requireEmptyQuery` — no query params allowed
- **Validation:** `providerNameSchema` — `^[a-zA-Z0-9_-]+$`, max 255
- **Response:** `{ data: { ...providerEntry, name, logo_url } }`
- **Errors:** `invalid_uri_params` (validation), `unknown_provider` (not found)

## Step 2 — Choose the bounded context

Provider reads belong in the `integrations` bounded context (the provider
catalog is shared with integration reads). The folder already exists:

```
src/nango_py/integrations/
  transport/routes.py      ← HTTP parsing, validation, response
  application/              ← use cases, gateway protocols
  domain/                   ← Provider, Integration dataclasses
  infrastructure/           ← SQLAlchemy repo, YAML provider catalog
```

If this were a new boundary, follow [add a new bounded context](../how-to/add-a-new-bounded-context.md).

## Step 3 — Implement the domain layer

The domain owns the data shape and invariants — no FastAPI, no SQLAlchemy:

```python
# src/nango_py/integrations/domain/provider.py

from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Provider:
    name: str
    display_name: str
    auth_mode: str
    authorization_url: str | None = None
    token_url: str | None = None
    # ...
```

Frozen dataclasses only. The domain imports nothing from transport or
infrastructure.

## Step 4 — Define the application port

The application layer needs a way to look up a provider. Define a Protocol:

```python
# src/nango_py/integrations/application/gateway.py

from typing import Protocol
from nango_py.integrations.domain.provider import Provider

class ProviderCatalog(Protocol):
    def get(self, name: str) -> Provider | None: ...
    def entry(self, name: str) -> dict[str, object] | None: ...
    def entries(self) -> dict[str, dict[str, object]]: ...
```

Protocols are async when they do I/O. The transport and use cases depend on
this Protocol, never on the concrete SQLAlchemy/YAML implementation.

## Step 5 — Implement the infrastructure adapter

The YAML provider catalog loads `packages/providers/providers.yaml` and
resolves aliases:

```python
# src/nango_py/integrations/infrastructure/provider_catalog.py

class YamlProviderCatalog:
    def __init__(self, entries: dict[str, dict[str, object]]):
        self._entries = entries

    @classmethod
    def from_path(cls, path: str | Path) -> "YamlProviderCatalog":
        with open(path) as f:
            raw = yaml.safe_load(f)
        # Resolve aliases, merge entries ...
        return cls(resolved)

    def get(self, name: str) -> Provider | None: ...
    def entry(self, name: str) -> dict[str, object] | None: ...
```

## Step 6 — Write the transport route

The transport layer only does HTTP: parse, validate, call use case, serialize:

```python
# In src/nango_py/integrations/transport/routes.py

@router.get("/providers/{provider}")
async def get_provider_route(
    provider: str,
    request: Request,
    auth: Annotated[AuthenticatedContext, Depends(api_auth)],
) -> JSONResponse:
    _require_empty_query(request)       # validation
    _validate_provider_name(provider)   # validation
    entry = provider_catalog.entry(provider)  # use case / catalog
    if entry is None:
        raise ProviderNotFound(provider)  # typed domain error
    return JSONResponse({"data": _provider_view(entry, provider, base)})  # serialize
```

The route does **not** own business logic. It validates transport shape, calls
one use case (or catalog lookup), and maps the result to JSON.

## Step 7 — Wire into the composition root

Register the router in `server/app.py`:

```python
app.include_router(
    create_integrations_router(
        get_integration, list_integrations, crud_service,
        provider_catalog=provider_catalog,
        base_public_url=resolved_base,
    )
)
```

See [wire a new route](../how-to/wire-a-new-route.md) for the full pattern.

## Step 8 — Write the test

Tests run against real migrated Postgres via testcontainers. The harness
applies the authoritative Knex migrations before tests run:

```python
# tests/integration/test_providers_route.py

async def test_get_provider_success(client, auth_headers):
    response = await client.get(
        "/providers/google",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["name"] == "google"
    assert "logo_url" in body["data"]
```

## Step 9 — Verify

```bash
cd nango-py
uv run ruff check .
uv run mypy
uv run pytest tests/integration/test_providers_route.py -v
```

All three must pass. The route is now ported.

## What you learned

Every route port follows this pattern:
1. Read the TypeScript controller (source of truth)
2. Place it in the right bounded context
3. Domain: frozen dataclass, no deps
4. Application: async Protocol port
5. Infrastructure: concrete adapter
6. Transport: validate → use case → serialize
7. Wire into composition root
8. Test against real Postgres
9. Verify ruff + mypy + pytest

Next: [verify parity with fixtures](./02-verify-parity-with-fixtures.md).