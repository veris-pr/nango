# How-to: Run the full test suite

> **Task:** Execute all verification gates for the Python port.

The port has five mandatory gates. All must pass before any boundary is
considered complete.

## Quick run

```bash
cd nango-py
uv run ruff check .
uv run mypy
uv run pytest -q
uv lock --check
uv build --wheel
```

## Gate 1 — Ruff (linting)

```bash
uv run ruff check .
uv run ruff check --fix .   # auto-fix where possible
```

Ruff enforces:
- Line length 100
- Import sorting (isort rules)
- Bugbear patterns
- Simplicity checks
- Pyupgrade rules

Config in `pyproject.toml` `[tool.ruff]`.

## Gate 2 — Mypy (strict type checking)

```bash
uv run mypy
```

Runs in strict mode. Common fixes:
- Missing `# type: ignore[import-untyped]` for packages without stubs
- Return type annotations on all public functions
- `Any` must be justified

Current coverage: 175+ source files checked.

## Gate 3 — Pytest (unit + contract + integration + parity)

```bash
# All tests
uv run pytest -q

# By suite
uv run pytest tests/unit/ -v          # domain + application unit tests
uv run pytest tests/contract/ -v      # fixture consumption
uv run pytest tests/integration/ -v   # real Postgres via testcontainers
uv run pytest tests/parity/ -v        # TS-vs-Py live comparison

# Single test
uv run pytest tests/integration/test_providers_route.py::test_get_provider_success -v
```

Integration tests use testcontainers — Docker must be running. They apply the
authoritative Knex migrations before the session starts.

### Test suite structure

```
tests/
  unit/         # domain logic, application use cases (no I/O)
  contract/     # consume TypeScript-generated fixtures
  integration/  # real Postgres, real SQLAlchemy, real httpx
  parity/       # live TS-vs-Py comparison (both servers running)
```

## Gate 4 — uv lock (dependency stability)

```bash
uv lock --check
```

Verifies `uv.lock` matches `pyproject.toml`. Run `uv lock` if deps change.

## Gate 5 — Wheel build (packaging)

```bash
uv build --wheel
```

Builds the wheel artifact. Must succeed for deployment.

## Integration test setup

Integration tests need:
- Docker running (testcontainers)
- Node.js available (for `tools/migrate.mjs` to apply Knex migrations)
- The Nango repo at the parent path (for migration files)

The conftest handles setup automatically:
1. Starts a Postgres container
2. Applies Knex migrations via `tools/migrate.mjs`
3. Creates an async session factory
4. Truncates tables between tests for isolation

## Parity test setup

Parity tests need **both** backends running:

```bash
# Terminal 1 — TypeScript backend
cd packages/server
npm run dev    # typically localhost:3003

# Terminal 2 — Python backend
cd nango-py
uv run python -m nango_py.run  # typically localhost:3004

# Terminal 3 — Run parity tests
cd nango-py
uv run pytest tests/parity/ -v
```

## CI gates

In CI, all five gates run in sequence. The full suite takes ~4-5 minutes
(integration tests dominate due to Postgres container startup).

## Common failures

| Failure | Cause | Fix |
|---------|-------|-----|
| testcontainers won't start | Docker not running | Start Docker Desktop |
| migrate.mjs fails | Node not found or wrong path | Ensure Node 18+ and repo root is correct |
| mypy import-untyped | Package lacks stubs | Add `# type: ignore[import-untyped]` |
| ruff F841 | Unused variable | Remove or prefix with `_` |
| Connection refused (parity) | One backend not running | Start both backends |