# How-to: Understand the data flow

> **Task:** Trace a request from HTTP entry to database and back.

Understanding the data flow is essential for debugging, adding features, and
reviewing code. Every request follows the same path through the DDD layers.

## The four-layer flow

```
HTTP Request
    │
    ▼
┌─────────────┐
│  Transport   │  Parse, validate, auth → call use case → serialize
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Application  │  Scope check → business logic → call gateway
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Domain       │  Invariants, typed errors, data shapes
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Infrastructure│  SQL query, crypto, external HTTP
└──────┬──────┘
       │
       ▼
   Database
```

## Tracing a real request: `GET /integrations/google`

### 1. HTTP enters FastAPI

```python
# src/nango_py/integrations/transport/routes.py

@router.get("/integrations/{unique_key}")
async def get_integration_route(
    unique_key: str,
    request: Request,
    auth: Annotated[AuthenticatedContext, Depends(api_auth)],
) -> JSONResponse:
    include = _parse_include(request)       # parse query params
    _validate_unique_key(unique_key)        # validate path param
    view = await get_integration.execute(    # call use case
        GetIntegrationRequest(unique_key=unique_key, include=include, context=auth)
    )
    return JSONResponse(serialize_view(view))  # serialize response
```

### 2. Auth dependency resolves

Before the route handler runs, `api_auth` resolves the bearer token:

```python
# src/nango_py/auth/transport/dependencies.py

async def api_auth(request: Request) -> AuthenticatedContext:
    gateway: AuthGateway = request.app.state.auth_gateway
    authorization = request.headers.get("authorization")
    # ... validate token format ...
    context = await gateway.resolve_by_secret_key(token)
    return context
```

### 3. Use case executes

```python
# src/nango_py/integrations/application/get_integration.py

class GetIntegration:
    async def execute(self, request: GetIntegrationRequest) -> PublicIntegrationView:
        self._authorize(request.context.scopes)  # scope check

        integration = await self._integrations.get_by_unique_key(
            environment_id=request.context.environment.id,
            unique_key=request.unique_key,
        )
        if integration is None:
            raise IntegrationNotFound(request.unique_key)

        provider = self._providers.get(integration.provider)
        if provider is None:
            raise ProviderNotFound(integration.provider)

        return self._build_view(integration, provider, request)
```

### 4. Gateway Protocol (injected)

The use case calls `self._integrations.get_by_unique_key()` — a Protocol
method. The concrete implementation is `SqlAlchemyIntegrationRepository`,
injected by the composition root.

### 5. Infrastructure queries Postgres

```python
# src/nango_py/integrations/infrastructure/sqlalchemy_integration_repository.py

class SqlAlchemyIntegrationRepository:
    async def get_by_unique_key(self, *, environment_id, unique_key) -> Integration | None:
        async with self._sf() as session:
            row = (
                await session.execute(
                    text("""
                        SELECT * FROM _nango_configs
                        WHERE environment_id = :eid
                          AND unique_key = :uk
                          AND deleted = false
                    """),
                    {"eid": environment_id, "uk": unique_key},
                )
            ).mappings().first()
        return _row_to_integration(row) if row else None
```

### 6. Domain view assembled

Back in the use case, `_build_view` constructs the `PublicIntegrationView`
domain object:

```python
return PublicIntegrationView(
    unique_key=integration.unique_key,
    provider=integration.provider,
    display_name=integration.display_name or provider.display_name,
    logo=f"{self._base_public_url}/images/template-logos/{integration.provider}.svg",
    ...
)
```

### 7. Transport serializes

```python
# src/nango_py/integrations/transport/serialize.py

def serialize_view(view: PublicIntegrationView) -> dict:
    result = {
        "unique_key": view.unique_key,
        "provider": view.provider,
        "display_name": view.display_name,
        "logo": view.logo,
        ...
    }
    # Conditional fields (only included when requested)
    if not isinstance(view.webhook_url, _NotSet):
        result["webhook_url"] = view.webhook_url
    return result
```

### 8. JSON response returned

```python
return JSONResponse(serialize_view(view))
```

## The error flow

When something goes wrong, the error flows differently:

```
Use case raises ApiError subclass
    │
    ▼
FastAPI exception handler catches it
    │
    ▼
ApiError.to_envelope() → {"error": {"code": "...", "message": "..."}}
    │
    ▼
JSONResponse with error status code
```

```python
# server/app.py
@app.exception_handler(ApiError)
async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(exc.to_envelope(), status_code=exc.status)
```

## The auth flow in detail

```
HTTP Request with Authorization: Bearer <token>
    │
    ▼
api_auth dependency
    │  - Extracts token from header
    │  - Validates UUID v4 format
    │  - Checks Nango-Is-Script header
    │
    ▼
AuthGateway.resolve_by_secret_key(token)
    │  - SHA-256 hash the token
    │  - Query api_secrets WHERE hashed = hash
    │  - Join _nango_environments + _nango_accounts
    │  - Decrypt the secret
    │
    ▼
AuthenticatedContext
    - account: Account
    - environment: Environment
    - secret: ApiSecret
    - scopes: Scopes (wildcard semantics)
    - auth_source: "api_secret" | "customer_key" | "env_var" | "connect_session"
```

## The proxy flow

Proxy requests have an additional step — credential refresh on 401:

```
POST /proxy/{path}
    │
    ▼
Transport: parse proxy headers, validate connection-id + provider-config-key
    │
    ▼
ProxyRequest.execute():
    1. Resolve integration + connection
    2. Refresh credentials if needed (OAuth2 token refresh)
    3. Build URL from provider proxy config + template interpolation
    4. Build headers from auth mode (Bearer, Basic, API key, etc.)
    5. Execute with retries:
       - Send request
       - On 401: refresh credentials, rebuild headers, retry
       - On 429/5xx: backoff and retry
       - On success: return response
    │
    ▼
Passthrough response (status + headers + body)
```

## Key principle

Data flows **down** through layers (transport → application → domain →
infrastructure) and results flow **up** (infrastructure → domain → application →
transport). Dependencies point **inward** — outer layers depend on inner
layers, never the reverse.

This means:
- You can test domain logic without a database
- You can test use cases with mock gateways
- You can swap infrastructure adapters without touching use cases
- Transport serialization is separate from domain logic