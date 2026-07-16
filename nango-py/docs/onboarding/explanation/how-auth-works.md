# Explanation: How auth works

> The complete auth pipeline from HTTP header to AuthenticatedContext.

## The auth pipeline

```
HTTP Request: Authorization: Bearer <token>
         │
         ▼
    ┌─────────────────┐
    │  FastAPI        │
    │  Dependency     │
    │  (api_auth)     │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │  Token parsing  │
    │  + validation   │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │  AuthGateway     │
    │  (resolve)      │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │  Authenticated  │
    │  Context        │
    └─────────────────┘
```

## Step 1 — FastAPI dependency

Every protected route uses `Depends(api_auth)`:

```python
@router.get("/integrations/{unique_key}")
async def get_integration_route(
    unique_key: str,
    auth: Annotated[AuthenticatedContext, Depends(api_auth)],
) -> JSONResponse:
    ...
```

FastAPI resolves the dependency before the route handler runs. If auth fails,
the route handler never executes.

## Step 2 — Token extraction

```python
# src/nango_py/auth/transport/dependencies.py

async def api_auth(request: Request) -> AuthenticatedContext:
    gateway: AuthGateway = request.app.state.auth_gateway

    authorization = request.headers.get("authorization")
    if authorization is None:
        raise MissingAuthHeader()

    token = _bearer_token(authorization)
    if token is None or token == "":
        raise MalformedAuthHeader()
```

The `_bearer_token` function splits on `"Bearer "` and takes the last part,
mirroring TypeScript's `authorizationHeader.split('Bearer ').pop()`.

## Step 3 — Token format validation

```python
    if not _compiled_uuid().fullmatch(token):
        raise InvalidSecretKeyFormat()
```

Secret keys are UUID v4 format. This mirrors TypeScript's `keyRegex` in
`access.middleware.ts`. Non-UUID tokens are rejected before hitting the
database.

## Step 4 — Script vs normal auth

```python
    is_script = request.headers.get("nango-is-script") == "true"
    if is_script:
        context = await gateway.resolve_by_internal_secret_key(token)
    else:
        context = await gateway.resolve_by_secret_key(token)
```

The `Nango-Is-Script: true` header routes through the internal secret path.
Internal secrets have a different tag in `api_secrets`.

## Step 5 — Gateway resolution

```python
# src/nango_py/auth/infrastructure/sqlalchemy_auth_gateway.py

async def resolve_by_secret_key(self, secret_key: str) -> AuthenticatedContext | None:
    hashed = hash_secret(secret_key, self._encryption_key)

    async with self._session_factory() as session:
        row = (
            await session.execute(_SECRET_QUERY, {"hash": hashed})
        ).mappings().first()

    if row is None:
        return None
    return self._context_from_row(row, auth_source="api_secret")
```

The SQL query joins `api_secrets` → `_nango_environments` → `_nango_accounts`,
returning everything needed to build an `AuthenticatedContext`.

## Step 6 — Context construction

```python
def _context_from_row(self, row, *, auth_source) -> AuthenticatedContext:
    account = Account(
        id=row["account_id"],
        name=row["account_name"],
        uuid=row["account_uuid"],
    )
    environment = Environment(
        id=row["environment_id"],
        name=row["environment_name"],
        account_id=row["environment_account_id"],
        uuid=row["environment_uuid"],
        is_production=row["environment_is_production"],
    )
    decrypted_secret = decrypt_api_secret(
        row["secret_value"], row["secret_iv"], row["secret_tag"],
        self._encryption_key,
    )
    secret = ApiSecret(
        id=row["secret_id"],
        environment_id=row["secret_environment_id"],
        display_name=row["secret_display_name"],
        secret=decrypted_secret,
        hashed=row["secret_hashed"],
        is_default=row["secret_is_default"],
    )
    return AuthenticatedContext(
        account=account,
        environment=environment,
        secret=secret,
        auth_source=auth_source,
        scopes=_WILDCARD_SCOPES,  # API secrets get all scopes
    )
```

API secrets (default auth) get wildcard scopes — they can do anything.
Customer keys get specific scopes from the `customer_keys` table.

## Auth modes

| Mode | Token format | Gateway method | Scopes |
|------|-------------|----------------|--------|
| API secret (default) | UUID v4 | `resolve_by_secret_key` | Wildcard (`*`) |
| Internal secret (script) | UUID v4 | `resolve_by_internal_secret_key` | Wildcard |
| Public key (deprecated) | UUID v4 | `resolve_by_public_key` | Wildcard |
| Customer key | Custom | `resolve_by_customer_key` | Specific |
| Connect session | `nango_connect_session_*` | `resolve_by_connect_session_token` | Wildcard |

## Scope checking

Use cases check scopes using the `Scopes` class:

```python
READ_SCOPE = "environment:integrations:read"
READ_CREDENTIALS_SCOPE = "environment:integrations:read_credentials"
REQUIRED_SCOPES = (READ_SCOPE, READ_CREDENTIALS_SCOPE)

class GetIntegration:
    def _authorize(self, scopes: Scopes) -> None:
        if not scopes.has_any(REQUIRED_SCOPES):
            raise Forbidden(REQUIRED_SCOPES)
```

`has_any` returns true if any of the required scopes match. Scope matching uses
TypeScript wildcard semantics:

- Exact: `"environment:syncs:execute"` == `"environment:syncs:execute"` ✓
- Wildcard: `"environment:*"` matches `"environment:syncs:execute"` ✓
- No match: `"environment:syncs:execute"` ≠ `"environment:actions:execute"` ✗

## Fail-closed principle

Auth always fails closed:
- Missing header → `MissingAuthHeader` (401)
- Malformed token → `MalformedAuthHeader` (401)
- Wrong format → `InvalidSecretKeyFormat` (401)
- No matching account → `UnknownAccount` (401)
- Missing scope → `Forbidden` (403)

There is no "default to authenticated" or "allow if unsure" path. Every
unauthenticated or unauthorized request is rejected with a typed error.

## Connect session auth

Connect session tokens (used by the Connect UI) follow a different path:

```python
async def connect_session_auth(request: Request) -> AuthenticatedContext:
    token = _bearer_token(authorization)
    if not token.startswith(_CONNECT_SESSION_TOKEN_PREFIX):
        raise MalformedAuthHeader()
    context = await gateway.resolve_by_connect_session_token(token)
    if context is None:
        raise UnknownAccount()
    return context
```

The gateway queries `connect_sessions` by token, checking expiry and deletion.
The returned context has wildcard scopes — the Connect UI can access any
endpoint the session allows.