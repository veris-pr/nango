# Tutorial: Run the server locally

> **Goal:** Start the Python backend, hit an API endpoint, and see a real
> response. By the end you'll have a running server you can develop against.

## Prerequisites

- Dev environment set up ([previous tutorial](./01-set-up-your-dev-environment.md))
- Docker running (for Postgres)
- A running Postgres instance (either via Docker or local install)

## Step 1 — Start a Postgres database

The backend needs a Postgres database with the Nango schema applied. The
easiest way is to use Docker:

```bash
docker run -d \
  --name nango-postgres \
  -e POSTGRES_USER=nango \
  -e POSTGRES_PASSWORD=nango \
  -e POSTGRES_DB=nango \
  -p 5432:5432 \
  postgres:16
```

## Step 2 — Apply Knex migrations

The TypeScript Knex migrations are authoritative. Apply them using the
migration script:

```bash
cd nango-py

# Set the database URL
export NANGO_DATABASE_URL="postgresql://nango:nango@localhost:5432/nango"

# Apply migrations (uses Node.js + Knex)
node tools/migrate.mjs "$NANGO_DATABASE_URL"
```

This creates all tables in the `nango` schema: `_nango_accounts`,
`_nango_environments`, `_nango_configs`, `_nango_connections`, etc.

## Step 3 — Seed test data

You need an account, environment, and API secret to authenticate. The
integration test seeds show how:

```bash
cat tests/integration/_seeds.py
```

For local development, you can insert a test environment directly:

```sql
-- Connect to the nango database
-- psql postgresql://nango:nango@localhost:5432/nango

INSERT INTO nango._nango_accounts (id, name, uuid)
VALUES (1, 'test-account', '00000000-0000-4000-8000-000000000001')
ON CONFLICT DO NOTHING;

INSERT INTO nango._nango_environments (id, name, account_id, uuid, public_key, is_production)
VALUES (1, 'dev', 1, '00000000-0000-4000-8000-000000000002',
        '00000000-0000-4000-8000-000000000003', false)
ON CONFLICT DO NOTHING;
```

Then create an API secret. The secret is stored encrypted + hashed. Use the
crypto helpers:

```bash
uv run python -c "
from nango_py.shared.crypto import hash_secret
secret = 'test-secret-key'
key = ''  # encryption key (empty for local dev)
print(f'Hash: {hash_secret(secret, key)}')
"
```

## Step 4 — Start the Python backend

```bash
cd nango-py

export NANGO_DATABASE_URL="postgresql+asyncpg://nango:nango@localhost:5432/nango"
export NANGO_SERVER_URL="http://localhost:3004"
export NANGO_ENCRYPTION_KEY=""

uv run python -m nango_py.run
```

The server starts on port 3004 (configurable via `NANGO_SERVER_URL`).

## Step 5 — Hit an API endpoint

```bash
# Health check
curl http://localhost:3004/orchestrator/v1/health
# → {"status":"ok"}

# Get providers (needs auth)
curl http://localhost:3004/providers \
  -H "Authorization: Bearer your-secret-key"
# → {"data": [{"name": "google", ...}, ...]}

# Get a single provider
curl http://localhost:3004/providers/google \
  -H "Authorization: Bearer your-secret-key"
# → {"data": {"name": "google", "auth_mode": "OAUTH2", ...}}
```

## Step 6 — Explore the OpenAPI spec

The Python backend auto-generates an OpenAPI spec:

```bash
curl http://localhost:3004/openapi.json | jq '.paths | keys'
```

This shows all 75 routes available.

## Step 7 — Run the TypeScript backend (for parity)

If you want to run parity tests, start the TypeScript backend too:

```bash
# In a separate terminal
cd packages/server
npm run dev
# → typically localhost:3003
```

Now both backends are running:
- TypeScript: `localhost:3003`
- Python: `localhost:3004`

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NANGO_DATABASE_URL` | — | App DB connection string (asyncpg format) |
| `NANGO_SERVER_URL` | `http://localhost:3003` | Base URL for webhook/callback URLs |
| `NANGO_PUBLIC_SERVER_URL` | `NANGO_SERVER_URL` | Public base URL for logos/links |
| `NANGO_ENCRYPTION_KEY` | — | AES-GCM encryption key for credentials |
| `NANGO_RECORDS_DATABASE_URL` | — | Records DB connection (separate from app DB) |

## What's next

- [Make your first change](./03-make-your-first-change.md)
- [Run your first test](./04-run-your-first-test.md)