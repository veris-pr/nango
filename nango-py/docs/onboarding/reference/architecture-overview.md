# Reference: Architecture overview

> System architecture, service boundaries, and how they fit together.

## System diagram

```
                    ┌─────────────────────────────────┐
                    │         Customer SDKs           │
                    │  (node-client, frontend, CLI)   │
                    └──────────────┬──────────────────┘
                                   │ HTTPS
                    ┌──────────────▼──────────────────┐
                    │      Public API (server)        │
                    │  75 routes: integrations,       │
                    │  connections, proxy, syncs,     │
                    │  records, auth flows, etc.      │
                    └──┬─────────┬──────────┬─────────┘
                       │         │          │
            ┌──────────▼──┐  ┌──▼───┐  ┌──▼──────────────┐
            │ Orchestrator  │ │ Jobs │  │ Persist Service  │
            │ (task API)   │ │(coord)│  │ (records CRUD)  │
            └──────┬───────┘ └──┬───┘  └──┬──────────────┘
                   │            │         │
            ┌──────▼──────┐  ┌──▼───┐  ┌─▼──────────────┐
            │  Scheduler   │ │Runner│  │  Records DB     │
            │ (Postgres)  │ │(Node)│  │ (partitioned)    │
            └─────────────┘ └──────┘  └─────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │      Shared Postgres             │
                    │  App DB | Scheduler DB |         │
                    │  Records DB | Keystore DB        │
                    └─────────────────────────────────┘
```

## Service boundaries

### Public API (server)
The main HTTP API. Receives all customer-facing requests: integrations,
connections, proxy, syncs, actions, records, auth flows, connect sessions,
webhooks. Authenticates via bearer token, enforces scope-based authorization.

**Python location:** `src/nango_py/server/app.py` (composition root)
**TS location:** `packages/server/lib/routes.public.ts`

### Orchestrator
HTTP API over the scheduler. Owns task creation (immediate + recurring),
dequeue, heartbeat, and state transitions. The public API dispatches syncs
and actions through the orchestrator.

**Python:** `src/nango_py/scheduler/`
**TS:** `packages/orchestrator/lib/`

### Scheduler
Postgres-backed task and schedule state machine. Owns dequeue locking, group
concurrency, retries, timeouts, heartbeat, and recurring schedule execution.

**Python:** `src/nango_py/scheduler/infrastructure/postgres_scheduler_repository.py`
**TS:** `packages/scheduler/lib/`

### Jobs
Coordinates work. Long-polls the orchestrator for tasks, prepares execution
context, dispatches to the Node runner, receives results, and updates the
orchestrator.

**Python:** `src/nango_py/jobs/`
**TS:** `packages/jobs/lib/`

### Runner
Executes customer JavaScript/TypeScript functions. **Stays in TypeScript** —
it runs customer code in a Node.js VM. The Python `jobs` service dispatches
to it via the runner boundary protocol.

**TS:** `packages/runner/lib/`

### Persist
HTTP service for records, checkpoints, and persistence operations. Used by
the runner SDK and jobs service.

**Python:** `src/nango_py/records/transport/routes.py`
**TS:** `packages/persist/lib/`

### Records
Database layer for stored records. Partitioned by `(connection_id, model)`.

**Python:** `src/nango_py/records/`
**TS:** `packages/records/lib/`

## DDD layering within each service

Every bounded context follows the same four-layer structure:

```
┌──────────────────────────────────────────────────┐
│ Transport                                        │
│ HTTP parsing, validation, response serialization │
│ Imports: FastAPI, Pydantic                       │
└──────────────────┬───────────────────────────────┘
                   │ depends on
┌──────────────────▼───────────────────────────────┐
│ Application                                      │
│ Use cases, gateway Protocols, scope checks       │
│ Imports: domain only (no FastAPI, no SQLAlchemy) │
└──────────────────┬───────────────────────────────┘
                   │ depends on
┌──────────────────▼───────────────────────────────┐
│ Domain                                           │
│ Frozen dataclasses, invariants, typed errors     │
│ Imports: nothing (no vendor libs)                │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ Infrastructure (parallel to the above)           │
│ SQLAlchemy repos, crypto, external HTTP clients   │
│ Implements: application Protocols                │
│ Imports: domain, SQLAlchemy, httpx, cryptography  │
└──────────────────────────────────────────────────┘
```

## Composition root

`server/app.py` is the only place that knows about concrete implementations.
It:
1. Creates infrastructure adapters (SQLAlchemy repos, YAML catalog)
2. Creates use cases, injecting adapters
3. Creates routers, injecting use cases
4. Registers routers with the FastAPI app
5. Registers the `ApiError` exception handler
6. Stores app-level state (auth gateway, httpx transport)

## Shared database

Both backends share the same Postgres instance:

| Database | Schema | Tables |
|----------|--------|--------|
| App DB | `nango` | `_nango_accounts`, `_nango_environments`, `_nango_configs`, `_nango_connections`, etc. |
| Records DB | `nango_records` | `records`, `record_data`, `record_counts` |
| Scheduler DB | `nango_scheduler` | `tasks`, `schedules` |
| Keystore DB | `nango_keystore` | `private_keys` |

Knex migrations (TypeScript) are authoritative. Python uses raw SQL against
the same schema — no ORM mappings, no Alembic migrations.

## What stays in TypeScript

- `packages/runner` — Node runner for customer JS/TS functions
- `packages/node-client` — server-side SDK
- `packages/frontend` — browser SDK
- `packages/connect-ui` — Connect UI React app
- `packages/cli` — CLI tool
- `packages/nango-yaml` — nango.yaml parser (CLI)
- `packages/runner-sdk` — SDK injected into customer functions

The Python backend must be **compatible** with all of these. They are not
ported; they are preserved.