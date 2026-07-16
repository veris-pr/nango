# Explanation: The cutover plan

> Why Nango replaces the TypeScript backend in one coordinated release,
> and what happens during the cutover window.

## The policy (from the user's stated decision)

> No production shadow/canary, mirroring, traffic splitting, TypeScript facade,
> or route-level cutover. Build and verify all Python backend boundaries
> offline, then replace the TypeScript backend in one coordinated release
> with verified TypeScript artifacts retained temporarily for emergency
> rollback during a stabilization window. Node runner and other TypeScript
> client/runtime packages remain.

## Why one coordinated release

### The database is shared

Both backends use the same Postgres database, same schemas, same encryption
keys. Running both simultaneously against production data creates:

- **Write conflicts** — Both backends writing to `_nango_connections`,
  `_nango_syncs`, `tasks`, `schedules`
- **Encryption race** — Both encrypting/decrypting with the same key; if
  formats drift, one corrupts the other's data
- **State divergence** — A sync triggered by TS creates state Python doesn't
  know about

### The service mesh is tightly coupled

```
Server → Orchestrator → Scheduler
                    ↓
              Jobs → Runner
                    ↓
              Persist → Records DB
```

Each hop has a typed contract. Mixing TS and Python services in the mesh
creates message-format risk. A clean cutover avoids this entirely.

### Risk concentration vs risk distribution

Gradual cutover distributes risk over weeks. Each day of dual-running is a
day where drift can silently corrupt data. A clean cutover concentrates risk
into one window — with full team attention, rehearsals, and rollback ready.

## Pre-cutover gates

Every boundary must pass before cutover is scheduled:

1. **Contract fixtures** — TypeScript-generated request/response fixtures
2. **Integration tests** — Real Postgres via testcontainers
3. **Parity tests** — Live TS-vs-Py comparison (both servers running)
4. **Security tests** — Auth fail-closed, authz, secret exposure
5. **Concurrency tests** — Idempotency, race conditions for writes
6. **Full-system tests** — End-to-end, load, failure-recovery
7. **Storage interoperability** — Bidirectional TS/Py data compatibility
8. **Non-production rehearsal** — Exact cutover + rollback in staging

## The cutover window

```
T-0:    Stop TypeScript backend processes (server, orchestrator, jobs, persist, scheduler)
T+1m:   Start Python backend processes (same ports, same database)
T+2m:   Health checks + smoke tests
T+5m:   Monitoring verification
        ├─ Green → Cutover complete. TS artifacts retained for rollback.
        └─ Red → Rollback: stop Python, restart TS. No rebuild needed.
```

## The stabilization window

After successful cutover, TypeScript artifacts remain deployable for a defined
period (duration decided before rehearsal):

- **If critical bug** → Rollback to TypeScript
- **Rollback is rehearsed** — No rebuild, no data migration. Verified artifacts
  are pre-staged.
- **After stabilization closes** → TypeScript backend retired per
  `dev/docs/PythonCoreTypescriptRetirement.md`

## What stays TypeScript

The cutover replaces the **backend core** only:

```
RETIRED (TS backend):
  packages/server        ← Public API → Python
  packages/orchestrator  ← Task API → Python
  packages/scheduler     ← Task state → Python
  packages/jobs          ← Work coordination → Python
  packages/persist       ← Records service → Python

RETAINED (TS):
  packages/runner        ← Customer JS/TS execution (stays Node)
  packages/runner-sdk    ← SDK in customer functions
  packages/node-client   ← Server-side SDK
  packages/frontend      ← Browser SDK
  packages/connect-ui    ← Connect UI
  packages/cli           ← CLI tool
  packages/nango-yaml    ← nango.yaml parser
```

The Python `jobs` service dispatches to the TypeScript runner — same as the
TypeScript `jobs` service did. The runner boundary protocol is unchanged.

## Why this works

1. **Parity is proven before cutover** — Every contract is frozen in fixtures
   and verified by parity tests. The cutover is a process swap, not a feature
   release.
2. **The database is shared** — No data migration needed. Python uses the
   same schema, same tables, same encryption format.
3. **Rollback is instant** — TypeScript artifacts are pre-staged. Rollback
   is "stop Python, start TypeScript" — no rebuild, no migration.
4. **Risk is bounded** — The stabilization window has a defined end. If no
   critical bugs appear, TypeScript is retired. If they do, rollback.

## What could go wrong

| Risk | Mitigation |
|------|-----------|
| Undetected contract drift | Parity tests + rehearsal |
| DB write conflict during cutover | One-directional cutover (stop TS first) |
| Encryption format mismatch | Bidirectional interoperability tests |
| Performance regression | Load tests in pre-cutover |
| Monitoring blind spot | Health checks + smoke tests post-cutover |
| Rollback failure | Rollback rehearsed before cutover |

## Key documents

- `dev/docs/PythonCoreImplementationPlan.md` — Full execution plan
- `dev/docs/PythonCoreStagedCutover.md` — Detailed cutover procedure
- `dev/docs/PythonCoreTypescriptRetirement.md` — Retirement plan
- `dev/docs/PythonCoreContractInventory.md` — Contract reference