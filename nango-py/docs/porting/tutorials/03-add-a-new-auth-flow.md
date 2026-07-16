# Tutorial: Add a new auth flow

> **Goal:** Port a new authentication mode (e.g. OAuth2 client credentials,
> JWT, or custom auth) from TypeScript to Python.

Nango supports many auth modes. Each one has a TypeScript controller in
`packages/server/lib/controllers/auth/` and an `auth_mode` in the provider
catalog. This tutorial shows how to add a new one.

## The pattern

All auth flow routes follow the same shape:
1. Receive credentials in the request body
2. Resolve the integration (provider config) by `provider_config_key`
3. Create a connection with the appropriate credential type
4. Return `{ connectionId, providerConfigKey }`

The difference between auth modes is the credential type and the
`expected_auth_mode` value.

## Step 1 — Read the TypeScript controller

For example, `packages/server/lib/controllers/auth/postJwt.ts`:
- Validates body with a Zod schema (credentials shape)
- Resolves the integration
- Calls `connectionService.upsertConnection` with credentials type `JWT`
- Runs connection hooks
- Returns the connection ID

## Step 2 — Find the expected_auth_mode

Look at the provider catalog entry (`packages/providers/providers.yaml`) for
the provider's `auth_mode`:

```yaml
google:
  auth_mode: OAUTH2
hubspot:
  auth_mode: OAUTH2
netsuite:
  auth_mode: TBA
```

Your new auth flow will use one of: `API_KEY`, `BASIC`, `OAUTH2`, `OAUTH2_CC`,
`TBA`, `TWO_STEP`, `JWT`, `BILL`, `SIGNATURE`, `APP_STORE`, `NONE`.

## Step 3 — Add the route to auth_flows

In `src/nango_py/auth_flows/transport/routes.py`, add a new route following
the existing pattern:

```python
@router.post("/auth/jwt/{provider_config_key}")
async def jwt_auth_route(
    provider_config_key: str,
    request: Request,
    auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    connection_id: str | None = Query(default=None, alias="connection_id"),
) -> JSONResponse:
    body = await _json_body(request)
    result = await create_auth_connection.execute(
        CreateAuthConnectionRequest(
            context=auth,
            provider_config_key=provider_config_key,
            connection_id=connection_id,
            credentials={
                "type": "JWT",
                **body,
            },
            expected_auth_mode="JWT",
        )
    )
    return JSONResponse(
        {"connectionId": result.connection_id,
         "providerConfigKey": result.provider_config_key}
    )
```

## Step 4 — Verify the use case handles it

`CreateAuthConnection` in `auth_flows/application/create_auth_connection.py`
already supports arbitrary credential types. It:
1. Resolves the integration by `provider_config_key`
2. Validates the `expected_auth_mode` matches the provider's `auth_mode`
3. Calls `connection_repository.upsert_connection` with the credentials

If the auth mode needs special handling (e.g., OAuth2 token exchange), add it
to the use case or create a separate strategy.

## Step 5 — Write a test

```python
# tests/integration/test_auth_flows_route.py

async def test_jwt_auth_creates_connection(client, auth_headers, seed_integration):
    response = await client.post(
        "/auth/jwt/my-integration",
        headers=auth_headers,
        json={"jwt": "eyJhbG..."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["providerConfigKey"] == "my-integration"
    assert body["connectionId"]
```

## Step 6 — Run the gates

```bash
uv run ruff check .
uv run mypy
uv run pytest tests/integration/test_auth_flows_route.py -v
```

## Common variations

### OAuth2 with token exchange

OAuth2 flows need an HTTP client to exchange the code for tokens. The
`oauth_callback_route` in the same file shows the pattern — it uses
`httpx.AsyncClient` to POST to the provider's `token_url`.

### Connect session auth

Some auth routes accept a connect session token instead of a secret key. Use
`connect_session_auth` dependency instead of `api_auth`:

```python
auth: Annotated[AuthenticatedContext, Depends(connect_session_auth)]
```

### Credential refresh

If the auth mode supports token refresh, wire the `CredentialRefresher` into
the proxy's retry loop (already done — see
`proxy/application/proxy_request.py`).

## What you learned

- All auth flows follow the same create-connection pattern
- The credential `type` and `expected_auth_mode` are the only real differences
- `CreateAuthConnection` handles the shared logic
- OAuth2 flows add an HTTP client for token exchange
- Connect session auth swaps `api_auth` for `connect_session_auth`