# Explanation: The cutover strategy

> Why the Python port uses one coordinated full replacement, not gradual
> cutover, shadowing, or traffic splitting.

## The decision

The cutover topology is fixed:

- **No production shadowing** — Python never receives production traffic
  during development
- **No canary releases** — No small percentage of traffic goes to Python
  first
- **No traffic splitting** — No route-level or account-level gradual cutover
- **No TypeScript facade** — TypeScript does not proxy to Python
- **One coordinated release** — When Python is ready, all TypeScript backend
  processes stop and Python starts in a single release window
- **Temporary rollback** — Verified TypeScript artifacts remain deployable
  for an emergency rollback during a defined stabilization window

## Why not gradual cutover

Gradual cutover (shadowing, canary, traffic splitting) is the standard
approach for risky migrations. Why not here?

### 1. Two backends sharing a database is dangerous

The TypeScript and Python backends share the same Postgres database, same
schemas, same encryption keys, same record formats. Running both against
production data simultaneously creates:

- **Write conflicts** — Both backends writing to `_nango_connections`,
  `_nango_syncs`, `tasks`, `schedules` with different transaction semantics
- **Encryption race** — Both backends encrypting/decrypting credentials;
  if formats drift, one corrupts the other's data
- **State divergence** — A sync triggered by TypeScript creates state that
  Python doesn't know about, and vice versa

### 2. The internal service mesh is tightly coupled

The server dispatches to the orchestrator, which dispatches to jobs, which
dispatches to the runner. Each hop has a typed contract. Mixing TypeScript
and Python services in the mesh creates message-format risk that's harder
to debug than a clean cutover.

### 3. Gradual cutover extends risk duration

Shadowing means running two backends for weeks or months. Every day of
dual-running is a day where drift can corrupt data. A clean cutover
concentrates risk into one window with full team attention.

### 4. The port is contract-complete before cutover

The port doesn't cutover until every boundary has:
- Contract fixtures
- Real-Postgres integration tests
- TypeScript-vs-Python parity tests
- Security tests (auth, authz, secret exposure)
- Concurrency/idempotency tests
- Full-system end-to-end tests
- A non-production rehearsal of the exact cutover and rollback

If all gates pass, the cutover risk is low. If any gate fails, cutover is
postponed.

## The cutover window

1. **Stop TypeScript backend processes** — server, orchestrator, jobs,
   persist, scheduler
2. **Start Python backend processes** — same ports, same database
3. **Verify** — health checks, smoke tests, monitoring
4. **If green** — cutover complete. TypeScript artifacts retained for rollback.
5. **If red** — Rollback: stop Python, restart TypeScript. No rebuild needed
   (verified artifacts are pre-staged).

## The stabilization window

After cutover, TypeScript artifacts remain deployable for a defined period
(exact duration to be decided before rehearsal). During this window:

- If a critical bug appears, rollback to TypeScript
- Rollback is rehearsed before cutover — no rebuild, no data migration
- After stabilization closes, TypeScript backend is retired per
  `dev/docs/PythonCoreTypescriptRetirement.md`

## What is NOT retired

The cutover retires the TypeScript **backend** only. These remain:

- `packages/node-client` — server-side SDK
- `packages/frontend` — browser SDK
- `packages/connect-ui` — Connect UI
- `packages/cli` — CLI
- `packages/nango-yaml` — nango.yaml parser
- `packages/runner` — Node runner
- `packages/runner-sdk` — runner SDK

The Node runner continues to execute customer JS/TS functions. The Python
`jobs` service dispatches to it via the runner boundary, same as TypeScript
did.

## Why this works

The port proves parity **before** cutover, not during. Every contract is
frozen in fixtures and verified by parity tests. The database schema is
shared, not migrated. The cutover is a process swap, not a data migration.

The risk is concentrated in one window with full attention, not spread
across weeks of dual-running where drift can silently corrupt data.

See also:
- `dev/docs/PythonCoreStagedCutover.md` — detailed cutover procedure
- `dev/docs/PythonCoreTypescriptRetirement.md` — retirement plan