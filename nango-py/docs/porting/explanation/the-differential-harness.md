# Explanation: The differential harness

> How the dual-backend parity testing harness proves TypeScript and Python
> produce identical responses.

## What it is

The differential harness (called "parity tests" in the codebase) runs the
same API request against both the TypeScript backend and the Python
backend simultaneously, then compares the responses byte-for-byte.

```
                     ┌──────────────┐
   same request ────→│  TS backend  │──→ response_ts
                     └──────────────┘
                     ┌──────────────┐
   same request ────→│  Py backend  │──→ response_py
                     └──────────────┘
                            │
                     compare response_ts == response_py
```

## Why it exists

Contract fixtures (frozen JSON) prove Python matches a **snapshot** of
TypeScript behavior. But snapshots can't capture:

- **Dynamic behavior** — Timestamps, pagination cursors, UUIDs generated at
  runtime
- **Database state** — How the backend reacts to existing connections,
  syncs, schedules in the DB
- **Error edge cases** — Rare paths that fixtures might not cover
- **Side effects** — What the backend writes to the DB as a result of a
  request

The differential harness closes this gap. It runs both backends live,
against the same database, and verifies they agree.

## How it works

### Setup

Both backends run simultaneously, each on its own port:

```bash
# TypeScript backend (e.g., port 3003)
cd packages/server && npm run dev

# Python backend (e.g., port 3004)
cd nango-py && uv run python -m nango_py.run
```

### Test structure

```python
# tests/parity/conftest.py

@pytest_asyncio.fixture
async def ts_client():
    async with httpx.AsyncClient(base_url="http://localhost:3003") as c:
        yield c

@pytest_asyncio.fixture
async def py_client():
    async with httpx.AsyncClient(base_url="http://localhost:3004") as c:
        yield c
```

### A parity test

```python
# tests/parity/test_integration_fixtures.py

async def test_integration_read_parity(ts_client, py_client, auth_headers):
    ts_resp = await ts_client.get("/integrations/google", headers=auth_headers)
    py_resp = await py_client.get("/integrations/google", headers=auth_headers)

    assert ts_resp.status_code == py_resp.status_code
    assert ts_resp.json() == py_resp.json()
```

## What gets normalized

Some values are inherently different between backends (timestamps, UUIDs).
The harness normalizes these before comparison:

```python
def normalize_for_parity(body: dict) -> dict:
    """Normalize nondeterministic values."""
    for key in ("created_at", "updated_at", "expires_at"):
        if key in body:
            body[key] = "<normalized:datetime>"
    return body
```

Normalization is conservative — only documented nondeterministic values are
normalized. Real differences are bugs, not noise.

## What a parity delta means

If `response_ts != response_py` after normalization, it's a **parity delta**.
Every delta must be:

1. **Diagnosed** — Find the field that differs
2. **Traced** — Read the TypeScript controller to understand the expected
   behavior
3. **Fixed** — Update the Python code to match
4. **Documented** — If intentionally accepted, document why

See [fix a parity delta](../how-to/fix-a-parity-delta.md).

## Current state

The parity suite covers core read endpoints:
- `GET /integrations/:uniqueKey`
- `GET /integrations`
- `GET /providers`
- `GET /connections`
- `GET /connections/:id`

As more endpoints are ported, their parity tests are added.

## Relationship to contract tests

| Test type | What it proves | When it runs |
|-----------|---------------|-------------|
| Contract | Python matches a frozen TypeScript snapshot | Offline (no TS server needed) |
| Parity | Python matches live TypeScript behavior | Online (both servers running) |

Contract tests are fast and run in every CI pipeline. Parity tests are
slower (need both servers) and run before cutover and in nightly CI.

## Why both are needed

Contract tests catch **regression** — if Python changes and no longer
matches the frozen snapshot, the test fails immediately.

Parity tests catch **drift** — if TypeScript changes (e.g., a new deploy
adds a field) and Python hasn't been updated, the parity test fails.

Together, they ensure the port stays faithful to the source of truth: the
TypeScript code.