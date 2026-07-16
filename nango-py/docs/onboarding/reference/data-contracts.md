# Reference: Data contracts

> API shapes, error envelopes, and database schemas the Python port must
> preserve. Condensed reference for daily use.

## API response shapes

### Integration

```json
{
  "unique_key": "google",
  "provider": "google",
  "display_name": "Google",
  "logo": "http://localhost:3003/images/template-logos/google.svg",
  "forward_webhooks": false,
  "created_at": "2024-01-01T00:00:00.000Z",
  "updated_at": "2024-01-01T00:00:00.000Z",
  "webhook_url": "http://localhost:3003/webhook/env-uuid/google",
  "credentials": {
    "type": "OAUTH2",
    "client_id": "...",
    "client_secret": "...",
    "scopes": "...",
    "webhook_secret": "..."
  }
}
```

- `webhook_url` and `credentials` are **conditional** — only present when
  requested via `?include=webhook,credentials`
- `credentials` requires `environment:integrations:read_credentials` scope

### Connection list

```json
{
  "connections": [
    {
      "id": 123,
      "connection_id": "my-conn",
      "provider_config_key": "google",
      "created_at": "2024-01-01T00:00:00.000Z",
      "updated_at": "2024-01-01T00:00:00.000Z",
      "tags": [],
      "metadata": {},
      "end_user": null,
      "active_logs": []
    }
  ]
}
```

- List response **never** includes credentials
- Key is `connections` (array), not `data`

### Connection single

```json
{
  "id": 123,
  "connection_id": "my-conn",
  "provider_config_key": "google",
  "credentials": {
    "type": "OAUTH2",
    "access_token": "..."
  },
  ...
}
```

- Single response **may** include credentials if `environment:connections:read_credentials` scope
- `refresh_token` is **always stripped** from credentials

### Provider

```json
{
  "data": {
    "name": "google",
    "display_name": "Google",
    "auth_mode": "OAUTH2",
    "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_url": "https://oauth2.googleapis.com/token",
    "logo_url": "http://localhost:3003/images/template-logos/google.svg",
    ...
  }
}
```

### Records

```json
{
  "next_cursor": null,
  "records": [
    {
      "id": "uuid",
      "external_id": "ext-123",
      "connection_id": 123,
      "model": "Contact",
      "data": { "name": "John" },
      "_nango_metadata": {
        "first_seen_at": "2024-01-01T00:00:00.000Z",
        "last_modified_at": "2024-01-01T00:00:00.000Z",
        "last_action": "UPDATED",
        "deleted_at": null,
        "cursor": ""
      }
    }
  ]
}
```

### Orchestrator task

```json
{
  "taskId": "uuid",
  "retryKey": "uuid"
}
```

## Error envelopes

### Direct (most errors)

```json
{"error": {"code": "unknown_integration", "message": "Integration not found"}}
```

### NangoError (auth errors)

```json
{"error": {"message": "Missing Authorization header", "code": "missing_auth_header", "payload": {}}}
```

### Validation

```json
{"error": {"code": "invalid_query_params", "errors": [{"code": "invalid_enum_value", "message": "...", "path": ["include"]}]}}
```

## Scope constants

| Scope | Who needs it |
|-------|-------------|
| `environment:integrations:read` | Read integrations without credentials |
| `environment:integrations:read_credentials` | Read integrations with credentials |
| `environment:integrations:write` | Create/update/delete integrations |
| `environment:integrations:list` | List integrations |
| `environment:connections:read` | Read connections without credentials |
| `environment:connections:read_credentials` | Read connections with credentials |
| `environment:connections:write` | Create/update/delete connections |
| `environment:connections:list` | List connections |
| `environment:syncs:execute` | Trigger/pause/start syncs |
| `environment:syncs:read` | Read sync status |
| `environment:syncs:manage` | Manage sync variants + frequency |
| `environment:actions:execute` | Trigger actions |
| `environment:records:read` | Read records |
| `environment:records:write` | Prune records |
| `environment:proxy` | Use proxy |
| `environment:deploy` | Deploy syncs |
| `environment:config:read` | Read env vars + scripts config |
| `environment:connect_sessions:write` | Create connect sessions |
| `environment:mcp` | Use MCP |
| `environment:*` | Wildcard (matches all) |

## Database schemas

### App DB (schema: `nango`)

Key tables and their relationships:

```
_nango_accounts (1) ──→ (N) _nango_environments
                          │
                          ├─→ (N) _nango_configs (integrations)
                          │         │
                          │         └─→ (N) _nango_connections
                          │                   │
                          │                   └─→ (N) _nango_syncs
                          │                             │
                          │                             └─→ (N) _nango_sync_jobs
                          │
                          ├─→ (N) api_secrets
                          ├─→ (N) customer_keys
                          └─→ (N) connect_sessions
```

### Records DB (schema: `nango_records`)

- `records` — partitioned by `(connection_id, model)`
- `record_data` — split JSON storage, partitioned
- `record_counts` — per-model counts + size

Record IDs: deterministic UUID5 from `(connection_id, model, external_id)`

### Scheduler DB (schema: `nango_scheduler`)

- `tasks` — UUID id, state machine, group concurrency, retries
- `schedules` — recurring task schedules

Task states: `CREATED → STARTED → SUCCEEDED/FAILED/CANCELLED/EXPIRED`

## Encryption

### Credential encryption (AES-256-GCM)

```python
from nango_py.shared.crypto import encrypt_aes_gcm, decrypt_aes_gcm

# Encrypt
ciphertext, iv, tag = encrypt_aes_gcm(json.dumps(creds), key)

# Decrypt
plaintext = decrypt_aes_gcm(ciphertext, iv, tag, key)
creds = json.loads(plaintext)
```

### Secret hashing (SHA-256)

```python
from nango_py.shared.crypto import hash_secret

hashed = hash_secret(secret_key, encryption_key)
```

## Pubsub event envelope

```json
{
  "idempotencyKey": "uuid",
  "subject": "usage",
  "type": "usage.records",
  "payload": {},
  "source": "server",
  "createdAt": "2024-01-01T00:00:00.000Z"
}
```

## Webhook signatures

### X-Nango-Hmac-Sha256 (current)

```
HMAC-SHA256(stable_json_body, environment_webhook_secret)
```

### X-Nango-Signature (deprecated)

```
SHA256(environment_secret + raw_payload)
```