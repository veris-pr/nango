# Reference: Database schema reference

> Tables, search paths, and encryption formats the Python port must preserve.

The TypeScript backend uses Knex migrations (in `packages/database/lib/migrations/`).
Python operates against the **same schemas** — it does not add Alembic migrations
until migration ownership is explicitly transferred.

## App database

Schema: `nango` (search_path)

### Core tables

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `_nango_accounts` | Accounts | `id`, `name`, `uuid` |
| `_nango_users` | Users | `id`, `email`, `account_id` |
| `_nango_environments` | Environments | `id`, `name`, `account_id`, `uuid`, `public_key`, `is_production` |
| `_nango_configs` | Integration configs | `id`, `unique_key`, `provider`, `environment_id`, `oauth_client_id`, `oauth_client_secret`, `oauth_scopes` |
| `_nango_connections` | Connections | `id`, `connection_id`, `provider_config_key`, `config_id`, `environment_id`, `credentials`, `credentials_iv`, `credentials_tag`, `metadata`, `tags`, `connection_config`, `deleted` |
| `_nango_sync_configs` | Sync/action configs | `id`, `environment_id`, `sync_name`, `type`, `models` |
| `_nango_syncs` | Sync instances | `id`, `connection_id`, `sync_config_id` |
| `_nango_sync_jobs` | Sync job runs | `id`, `sync_id`, `status` |
| `_nango_active_logs` | Active log pointers | `connection_id`, `type`, `log_id`, `active` |
| `_nango_oauth_sessions` | OAuth sessions | `id`, `environment_id`, `provider_config_key` |
| `end_users` | End users | `id`, `connection_id`, `end_user_id`, `email` |
| `connect_sessions` | Connect sessions | `id`, `environment_id`, `token`, `expires_at`, `deleted_at` |
| `api_secrets` | API secrets | `id`, `environment_id`, `secret`, `iv`, `tag`, `hashed`, `is_default`, `display_name` |
| `customer_keys` | Customer keys | `id`, `environment_id`, `api_key`, `hashed`, `scopes` |

### Connection credentials encryption

Credentials are stored in `_nango_connections.credentials` as AES-256-GCM
encrypted JSON:

- `credentials` — encrypted ciphertext (base64)
- `credentials_iv` — initialization vector (base64)
- `credentials_tag` — authentication tag (base64)

Python uses `cryptography` library's AESGCM. The encryption key is the
environment's secret key (same as TypeScript's `encryption.manager.ts`).

```python
from nango_py.shared.crypto import encrypt_aes_gcm, decrypt_aes_gcm

# Encrypt
ciphertext, iv, tag = encrypt_aes_gcm(plaintext_json, key)

# Decrypt
plaintext = decrypt_aes_gcm(ciphertext, iv, tag, key)
```

### API secret hashing

API secrets are stored as SHA-256 hashes in `api_secrets.hashed`:

```python
from nango_py.shared.crypto import hash_secret

hashed = hash_secret(secret_key, encryption_key)
```

## Records database

Schema: `nango_records` (separate search_path)

### Tables

| Table | Purpose | Partitioning |
|-------|---------|--------------|
| `records` | Record metadata | By `(connection_id, model)` |
| `record_data` | Record JSON data (split from metadata) | By `(connection_id, model)` |
| `record_counts` | Per-model counts + size | Not partitioned |

### Record ID generation

Records use deterministic UUID5 IDs from `(connection_id, model, external_id)`:

```python
import uuid
record_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{connection_id}:{model}:{external_id}"))
```

### Data hash

Records store an MD5 hash of the JSON data for change detection:

```python
import hashlib
data_hash = hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()
```

## Scheduler database

Schema: `nango_scheduler` (separate search_path)

### Tables

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `tasks` | Task state | `id` (UUID), `name`, `payload`, `group_key`, `state`, `heartbeat`, `output`, `retry_key`, `owner_key` |
| `schedules` | Recurring schedules | `id` (UUID), `name`, `state`, `frequency_ms`, `payload`, `next_execution_at` |

Task states: `CREATED`, `STARTED`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `EXPIRED`

## Keystore database

Schema: `nango_keystore`

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `private_keys` | Encrypted private keys | `id`, `account_id`, `environment_id`, `entity`, `encrypted_key`, `hashed_key`, `expires_at` |

Entity enum: `session`, `connection`, `environment`

## Connection in tests

Integration tests use testcontainers Postgres. The harness applies Knex
migrations via `tools/migrate.mjs` (Node.js) so Python tests run against the
exact schema the TypeScript backend produces:

```python
# tests/integration/conftest.py
container = PostgresContainer("postgres:16")
# Apply migrations
subprocess.run(["node", MIGRATE_SCRIPT, container_url], check=True)
# Create async session factory
engine = create_async_engine(asyncpg_url, connect_args={"server_settings": {"search_path": "nango"}})
```

## Important: no Alembic

Python does **not** add Alembic migrations. Knex migrations remain authoritative
until migration ownership is explicitly transferred. Python SQLAlchemy queries
use raw `text()` SQL against the existing schema, not ORM mappings.