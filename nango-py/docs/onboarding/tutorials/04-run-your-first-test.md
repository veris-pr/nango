# Tutorial: Run your first test

> **Goal:** Understand the four test suites, run them, and interpret results.

The Python port has four test suites, each serving a different purpose.

## The four suites

```
tests/
  unit/         # Domain + application logic (no I/O)
  contract/     # TypeScript-generated fixtures consumed by Python
  integration/  # Real Postgres via testcontainers
  parity/       # Live TS-vs-Py comparison (both servers)
```

## Suite 1 — Unit tests

**What they test:** Domain invariants, use case logic, pure functions.

**What they need:** Nothing (no Docker, no DB).

```bash
cd nango-py
uv run pytest tests/unit/ -v
```

Example:

```python
# tests/unit/auth/test_scopes.py

def test_exact_scope_match():
    scopes = Scopes(granted=("environment:syncs:execute",))
    assert scopes.has("environment:syncs:execute")

def test_wildcard_scope_match():
    scopes = Scopes(granted=("environment:*",))
    assert scopes.has("environment:syncs:execute")
    assert scopes.has("environment:integrations:read")

def test_no_scope_match():
    scopes = Scopes(granted=("environment:syncs:execute",))
    assert not scopes.has("environment:actions:execute")
```

Unit tests are fast (~seconds) and run on every save.

## Suite 2 — Contract tests

**What they test:** Python consumes frozen TypeScript fixtures and matches
expected output.

**What they need:** No Docker (fixtures are JSON files).

```bash
cd nango-py
uv run pytest tests/contract/ -v
```

Example:

```python
# tests/contract/test_fixtures_load.py

def test_fixture_loads(fixture_file):
    fixture = json.loads(Path(fixture_file).read_text())
    expected = fixture["response"]
    # Run request against Python app...
    assert response.json() == expected["body"]
```

Contract tests prove Python matches the TypeScript contract snapshot.

## Suite 3 — Integration tests

**What they test:** Real SQLAlchemy queries against real Postgres, real
httpx calls, real encryption.

**What they need:** Docker running (for testcontainers Postgres).

```bash
cd nango-py
uv run pytest tests/integration/ -v
```

What happens behind the scenes:
1. `conftest.py` starts a Postgres container
2. Runs `tools/migrate.mjs` (Node.js) to apply Knex migrations
3. Creates an async session factory
4. Each test gets a truncated schema for isolation
5. Tests make real HTTP requests via `httpx.AsyncClient`

Example:

```python
# tests/integration/test_providers_route.py

async def test_get_provider_success(client, auth_headers):
    response = await client.get(
        "/providers/google",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "google"
```

Integration tests are slower (~4 min for the full suite) because of Postgres
container startup and migration application.

## Suite 4 — Parity tests

**What they test:** Python and TypeScript backends produce identical
responses for the same request.

**What they need:** Both backends running + Docker.

```bash
# Terminal 1: Start TypeScript backend
cd packages/server && npm run dev  # localhost:3003

# Terminal 2: Start Python backend
cd nango-py && uv run python -m nango_py.run  # localhost:3004

# Terminal 3: Run parity tests
cd nango-py
uv run pytest tests/parity/ -v
```

Example:

```python
# tests/parity/test_integration_fixtures.py

async def test_parity(ts_client, py_client, auth_headers):
    ts_resp = await ts_client.get("/integrations/google", headers=auth_headers)
    py_resp = await py_client.get("/integrations/google", headers=auth_headers)
    assert ts_resp.status_code == py_resp.status_code
    assert ts_resp.json() == py_resp.json()
```

## Running everything

```bash
cd nango-py

# All tests (except parity, which needs both servers)
uv run pytest -q

# Just unit (fastest)
uv run pytest tests/unit/ -q

# Just one test
uv run pytest tests/integration/test_providers_route.py::test_get_provider_success -v

# With output
uv run pytest -v -s

# Stop on first failure
uv run pytest -x

# Run a specific pattern
uv run pytest -k "provider" -v
```

## Interpreting results

```
........................................................................ [ 34%]
........................................................................ [ 69%]
................................................................         [100%]
208 passed in 220.48s
```

- `.` = passed
- `F` = failed
- `E` = error (collection/import failure)
- `s` = skipped

## Common test fixtures

Tests use pytest fixtures for setup:

```python
@pytest_asyncio.fixture
async def client(app):
    """httpx client wired to the FastAPI app."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

@pytest.fixture
def auth_headers():
    """Bearer token for test authentication."""
    return {"Authorization": "Bearer test-secret-key"}
```

## When to write which test

| Change | Unit | Contract | Integration | Parity |
|--------|------|----------|-------------|--------|
| Domain logic | ✅ | — | — | — |
| Use case | ✅ | — | ✅ | — |
| Route | — | ✅ | ✅ | ✅ |
| DB query | — | — | ✅ | — |
| Error envelope | ✅ | ✅ | ✅ | ✅ |
| Provider catalog | ✅ | — | ✅ | — |

## What's next

- [Add a new API endpoint](../how-to/add-a-new-endpoint.md)
- [Architecture overview](../reference/architecture-overview.md)