# Reference: Data flow reference

> Detailed request lifecycle through all layers, with code references.

## Request lifecycle: read endpoint

```
1. HTTP Request arrives
   │
   ├─→ FastAPI router matches path + method
   │
2. Auth dependency resolves (api_auth)
   │   ├─ Extract Authorization header
   │   ├─ Validate Bearer token format (UUID v4)
   │   ├─ Call AuthGateway.resolve_by_secret_key(token)
   │   │   ├─ SHA-256 hash token
   │   │   ├─ Query: SELECT from api_secrets JOIN environments JOIN accounts
   │   │   ├─ Decrypt secret (AES-GCM)
   │   │   └─ Return AuthenticatedContext (account + environment + scopes)
   │   └─ Return AuthenticatedContext or raise (MissingAuthHeader, InvalidSecretKeyFormat, UnknownAccount)
   │
3. Route handler runs
   │   ├─ Parse + validate query params → ValidationApiError on failure
   │   ├─ Validate path params → ValidationApiError on failure
   │   └─ Call use case: get_integration.execute(request)
   │
4. Use case executes
   │   ├─ Scope check: scopes.has_any(REQUIRED_SCOPES) → Forbidden on failure
   │   ├─ Call gateway: integration_repository.get_by_unique_key(...)
   │   │   └─ SQL: SELECT from _nango_configs WHERE environment_id = ? AND unique_key = ?
   │   ├─ If None → raise IntegrationNotFound
   │   ├─ Call catalog: provider_catalog.get(integration.provider)
   │   ├─ If None → raise ProviderNotFound
   │   └─ Build PublicIntegrationView (domain object)
   │
5. Transport serializes
   │   ├─ Convert domain view → dict with camelCase keys
   │   ├─ Handle NOT_SET (omit) vs None (null) vs value
   │   └─ Convert datetimes to ISO 8601 with Z suffix
   │
6. JSONResponse returned
   │   └─ {"unique_key": "google", "provider": "google", "display_name": "Google", ...}
   │
7. HTTP Response sent
```

## Request lifecycle: write endpoint (connection create)

```
1. HTTP Request: POST /connections with JSON body
   │
2. Auth dependency resolves (api_auth)
   │
3. Route handler runs
   │   ├─ Parse JSON body
   │   ├─ Create CreateConnectionRequest (with context, credentials, metadata, tags)
   │   └─ Call crud_service.create(request)
   │
4. Use case executes (ConnectionCrudService.create)
   │   ├─ Resolve integration by provider_config_key
   │   ├─ Encrypt credentials (AES-GCM)
   │   ├─ SQL: INSERT INTO _nango_connections (...) ON CONFLICT UPDATE
   │   └─ Return created connection
   │
5. Transport serializes
   │   └─ {"connectionId": "...", "providerConfigKey": "..."}
   │
6. JSONResponse returned
```

## Request lifecycle: proxy

```
1. HTTP Request: POST /proxy/{path} with proxy headers
   │   ├─ Connection-Id: required
   │   ├─ Provider-Config-Key: required
   │   ├─ Retries: optional (default 0)
   │   ├─ Base-Url-Override: optional
   │   └─ Nango-Proxy-*: forwarded to upstream
   │
2. Auth dependency resolves (api_auth)
   │   └─ Scope check: environment:proxy
   │
3. ProxyRequest.execute()
   │   ├─ Resolve integration by provider_config_key
   │   ├─ Resolve connection by connection_id + provider_config_key
   │   ├─ Refresh credentials if needed (OAuth2 token refresh)
   │   ├─ Check base URL override denylist
   │   ├─ Build URL: provider.proxy.base_url + endpoint (with ${} interpolation)
   │   ├─ Build headers: per auth mode (Bearer, Basic, API key, custom)
   │   │
   │   └─ Execute with retries:
   │       ├─ Send request via httpx
   │       ├─ On 200-399: return ProxyResponse
   │       ├─ On 401: refresh credentials → rebuild headers → retry
   │       ├─ On 429/5xx: backoff → retry (up to max_retries)
   │       └─ On other: return error response
   │
4. Response passthrough
   └─ Return upstream status + headers + body as-is
```

## Request lifecycle: sync trigger

```
1. HTTP Request: POST /sync/trigger with body
   │   ├─ syncs: ["sync_name", {"name": "sync", "variant": "v1"}]
   │   ├─ connection_id: optional
   │   └─ provider_config_key: optional
   │
2. Auth dependency resolves (api_auth)
   │   └─ Scope check: environment:syncs:execute
   │
3. Route handler runs
   │   ├─ Resolve provider_config_key (body or header)
   │   ├─ Resolve connection_id (body or header)
   │   ├─ Validate integration exists
   │   └─ For each sync:
   │       └─ OrchestratorService.create_immediate(ImmediateTaskInput)
   │           ├─ SQL: INSERT INTO tasks (...)
   │           └─ Return task_id + retry_key
   │
4. JSONResponse: {"data": {"taskId": "...", "retryKey": "..."}}
```

## Error flow

```
Use case raises ApiError subclass
   │
   ├─ ApiError (direct envelope)
   │   └─ {error: {code: "...", message: "..."}}
   │
   ├─ NangoApiError (NangoError envelope)
   │   └─ {error: {message: "...", code: "...", payload: {}}}
   │
   └─ ValidationApiError (validation envelope)
       └─ {error: {code: "...", errors: [{code, message, path}]}}
   │
   ▼
FastAPI exception handler catches ApiError
   │
   ├─ exc.to_envelope() → dict
   ├─ JSONResponse(body, status_code=exc.status)
   │
   ▼
HTTP error response sent to client
```

## Auth resolution flow

```
Authorization: Bearer <token>
   │
   ├─ Is Nango-Is-Script: true?
   │   └─ Yes → resolve_by_internal_secret_key(token)
   │       └─ Query: api_secrets WHERE hashed = SHA256(token) AND tag = 'internal'
   │
   ├─ Token starts with "nango_connect_session_"?
   │   └─ Yes → resolve_by_connect_session_token(token)
   │       └─ Query: connect_sessions WHERE token = ? AND expires_at > NOW()
   │
   └─ Otherwise → resolve_by_secret_key(token)
       ├─ Hash: SHA256(token + encryption_key)
       ├─ Query: api_secrets WHERE hashed = hash AND is_default = true
       ├─ JOIN: _nango_environments + _nango_accounts
       ├─ Decrypt: AES-GCM(secret, iv, tag, encryption_key)
       └─ Return: AuthenticatedContext with wildcard scopes
   │
   ▼
AuthenticatedContext
   ├─ account: Account(id, name, uuid)
   ├─ environment: Environment(id, name, account_id, uuid, is_production)
   ├─ secret: ApiSecret(id, environment_id, display_name, secret, hashed, is_default)
   ├─ scopes: Scopes(granted=(...))  # tuple of scope strings
   └─ auth_source: "api_secret" | "customer_key" | "env_var" | "connect_session"
```

## Credential encryption flow

```
Plaintext credentials (dict)
   │
   ├─ JSON serialize → string
   ├─ AES-256-GCM encrypt with environment encryption key
   │   ├─ ciphertext = encrypt(plaintext, key)
   │   ├─ iv = generated nonce
   │   └─ tag = authentication tag
   │
   └─ Store in _nango_connections:
       ├─ credentials = base64(ciphertext)
       ├─ credentials_iv = base64(iv)
       └─ credentials_tag = base64(tag)

Decrypt (reverse):
   ├─ Read credentials, credentials_iv, credentials_tag from DB
   ├─ base64 decode each
   ├─ AES-256-GCM decrypt
   └─ JSON parse → credentials dict
```