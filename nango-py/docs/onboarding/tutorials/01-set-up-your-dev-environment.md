# Tutorial: Set up your dev environment

> **Goal:** Get the Nango repo cloned, dependencies installed, and the Python
> backend building. By the end you'll be ready to run tests.

## Prerequisites

Install these before starting:

| Tool | Version | Why |
|------|---------|-----|
| Python | 3.12+ | Python backend runtime |
| Node.js | 18+ | TypeScript backend, Knex migrations, CLI |
| Docker | latest | Postgres testcontainers for integration tests |
| `uv` | latest | Python package manager (faster than pip) |
| Git | latest | Clone the repo |

### Install uv

```bash
# macOS
brew install uv

# Or via the official installer
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Step 1 — Clone the repo

```bash
git clone <repo-url> nango
cd nango
```

## Step 2 — Explore the structure

```
nango/
  packages/           # TypeScript backend (source of truth for contracts)
    server/           # Public API server
    orchestrator/      # Task scheduling API
    scheduler/         # Postgres-backed task state
    jobs/              # Work coordination
    runner/            # Customer JS/TS function execution
    persist/           # Records persistence service
    records/           # Records database layer
    providers/         # providers.yaml — 785 provider definitions
    types/             # Shared TypeScript types (Endpoint<> contracts)
    ...
  nango-py/           # Python backend (the port)
    src/nango_py/      # All Python source
    tests/             # Unit, contract, integration, parity tests
    tools/             # Migration scripts, crypto vector generators
    docs/              # This documentation
  dev/docs/           # Planning docs (implementation plan, cutover, contracts)
  packages/database/lib/migrations/  # Knex migrations (authoritative schema)
```

## Step 3 — Set up the Python backend

```bash
cd nango-py
uv sync --extra dev
```

This installs all runtime and dev dependencies into a virtual environment
managed by `uv`.

## Step 4 — Verify the Python backend builds

```bash
cd nango-py

# Lint
uv run ruff check .

# Type check (strict mode)
uv run mypy

# Build
uv build --wheel
```

All three must pass. If `mypy` reports `import-untyped` errors, that's
expected for packages without stubs — they're handled with
`# type: ignore[import-untyped]`.

## Step 5 — Set up the TypeScript backend (optional, for parity tests)

```bash
cd packages
npm install
```

You only need this if you plan to run parity tests (which compare both
backends live). For most development, the Python tests alone are sufficient.

## Step 6 — Start Docker

Integration tests use testcontainers to spin up a Postgres container. Ensure
Docker Desktop (or Docker daemon) is running:

```bash
docker info
```

If this fails, start Docker Desktop or your Docker daemon.

## Step 7 — Run your first test

```bash
cd nango-py
uv run pytest tests/unit/ -v
```

Unit tests don't need Docker. They test domain logic and application use
cases in isolation.

Now try an integration test (needs Docker):

```bash
uv run pytest tests/integration/test_providers_route.py -v
```

This will:
1. Start a Postgres container
2. Apply Knex migrations (via Node.js `tools/migrate.mjs`)
3. Run the test against real Postgres
4. Tear down the container

## Step 8 — Explore the code

Start with the composition root to see how everything is wired:

```bash
cat src/nango_py/server/app.py
```

Then look at a simple bounded context to understand the DDD pattern:

```bash
# Domain layer (no deps)
cat src/nango_py/auth/domain/context.py

# Application layer (Protocols + use cases)
cat src/nango_py/integrations/application/get_integration.py

# Infrastructure (concrete adapter)
cat src/nango_py/integrations/infrastructure/provider_catalog.py

# Transport (HTTP)
cat src/nango_py/integrations/transport/routes.py
```

## Common issues

| Issue | Fix |
|-------|-----|
| `uv: command not found` | Install uv: `brew install uv` |
| `testcontainers won't start` | Start Docker Desktop |
| `migrate.mjs fails` | Ensure Node 18+ is installed and `nango-py/tools/migrate.mjs` can find the repo root |
| `mypy: import-untyped` | Expected — add `# type: ignore[import-untyped]` for stubless packages |
| `ruff: F841` | Unused variable — remove or prefix with `_` |

## What's next

- [Run the server locally](./02-run-the-server-locally.md)
- [Make your first change](./03-make-your-first-change.md)