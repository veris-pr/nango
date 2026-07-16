# How-to: Wire a new route into the composition root

> **Task:** Register a new router in `server/app.py` so it's reachable.

The composition root (`src/nango_py/server/app.py`) is the only place that
knows about concrete implementations. It wires infrastructure adapters into
use cases, and use cases into routers, and routers into the FastAPI app.

## Step 1 — Read the existing wiring pattern

Open `server/app.py`. Every boundary follows this pattern:

```python
# 1. Create the infrastructure adapter
connection_repo = SqlAlchemyConnectionRepository(
    session_factory, encryption_key=encryption_key
)

# 2. Create use cases, injecting adapters
list_connections = ListConnections(connection_repository=connection_repo)
get_connection = GetConnection(
    connection_repository=connection_repo,
    integration_repository=integration_repo,
)

# 3. Create the router, injecting use cases
app.include_router(
    create_connections_router(list_connections, get_connection, connection_crud)
)
```

## Step 2 — Add your wiring

After your use case is created, add the router include:

```python
app.include_router(create_my_router(get_entity))
```

If your router needs additional dependencies (e.g., provider catalog, base URL),
pass them as keyword arguments:

```python
app.include_router(
    create_integrations_router(
        get_integration, list_integrations, crud_service,
        provider_catalog=provider_catalog,
        base_public_url=resolved_base,
    )
)
```

## Step 3 — Add the import

At the top of `server/app.py`, add the import in the right section:

```python
from nango_py.<context>.transport.routes import create_my_router
```

If you also created a new use case or adapter, import those too:

```python
from nango_py.<context>.application.get_entity import GetEntity
from nango_py.<context>.infrastructure.sqlalchemy_repository import SqlAlchemyMyRepository
```

## Step 4 — Order matters

Infrastructure adapters must be created **before** use cases that depend on
them. Use cases must be created **before** routers that depend on them.

If your new use case depends on `provider_catalog`, make sure
`provider_catalog` is created earlier in the function:

```python
# provider_catalog must exist before this line
my_use_case = MyUseCase(provider_catalog=provider_catalog)
```

## Step 5 — Store app state if needed

If your route needs app-level state (e.g., the auth gateway, httpx transport),
store it on `app.state`:

```python
app.state.auth_gateway = auth_gateway
app.state.httpx_transport = httpx_transport
```

Access it in the route or dependency via `request.app.state`:

```python
async def api_auth(request: Request) -> AuthenticatedContext:
    gateway: AuthGateway = request.app.state.auth_gateway
    ...
```

## Step 6 — Verify

```bash
uv run ruff check src/nango_py/server/app.py
uv run mypy
uv run pytest -x
```

Check that the route appears in the OpenAPI spec:

```bash
uv run python -c "
from nango_py.server.app import create_app
...
paths = sorted(app.openapi()['paths'].keys())
for p in paths:
    if '/my' in p:
        print(p)
"
```

## Common pitfalls

- **Duplicate provider_catalog creation** — don't create it twice; reuse the
  one already in `app.py`
- **Missing `__init__.py`** — ensure new packages have `__init__.py` files
- **Circular imports** — the composition root imports from all contexts; keep
  context-to-context imports in `application/gateway.py` Protocols only
- **Forgetting to pass `encryption_key`** — most SQLAlchemy adapters need it