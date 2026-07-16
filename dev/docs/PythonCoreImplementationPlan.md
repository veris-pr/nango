# Python core implementation plan

**Status:** Approved restart; Phase 0 in progress  
**Active implementation:** `nango-py/`  
**Archived prototype:** `python-core-spike/`  
**Last updated:** 2026-07-10

## End goal

Replace Nango TypeScript backend core responsibilities with production-grade Python implementations while preserving every customer-visible and service-visible contract required by the retained TypeScript SDKs, UIs, CLI, and Node runner.

Python replaces TypeScript in one coordinated release only after every required boundary has contract parity, real storage compatibility, full-system validation, release rehearsal, and rollback rehearsal. Python source coverage or passing unit tests alone do not establish readiness.

## Restart rationale

The archived `python-core-spike/` explored broad Python coverage, but it did not establish a production-safe vertical slice. Review found fail-open authentication, missing authorization scopes, incompatible persist contracts and encryption, broken real-Postgres mappings, volatile scheduling, and no wired jobs-to-runner path. Its green tests primarily validated Python-owned behavior through in-memory or fake adapters rather than TypeScript parity.

The new implementation therefore starts contract-first and risk-first. Prototype code is not copied by default.

## Accepted decisions

- Use `nango-py/` for active implementation.
- Keep `python-core-spike/` as read-only reference until useful artifacts have been independently verified or replaced.
- Use Python 3.12+, Pydantic v2, SQLAlchemy 2 async, asyncpg, FastAPI/Starlette for HTTP adapters, and asyncio-compatible libraries.
- Keep existing Knex migrations authoritative during migration. Python must operate against schemas produced by current TypeScript migrations.
- Keep TypeScript SDKs, UIs, CLI, `nango-yaml` CLI parsing, runner SDK, and Node runner.
- Develop Python in incremental vertical slices, but send no production traffic to Python until the complete replacement is ready.
- Replace the TypeScript backend in one coordinated full cutover; do not add production shadowing, canaries, traffic splitting, mirroring, or route-level cutover.
- Keep verified TypeScript backend artifacts deployable for emergency rollback during a defined stabilization window.
- Keep billing and new telemetry work out of scope. Usage/metering remains in scope when its boundary is scheduled.
- Build one route family or service boundary at a time during development. No broad horizontal skeleton.
- Use explicit production dependencies. Missing DB, queue, keystore, or gateway config must fail startup; production code must never silently select an in-memory implementation.
- Generate compatibility evidence from TypeScript behavior. Handwritten Python-only round trips are not parity tests.

## Cutover strategy

Traffic topology is decided: Python receives no production traffic during implementation. Offline fixtures, differential tests, migrated-schema integration tests, end-to-end tests, load/failure tests, and a non-production release rehearsal establish readiness.

When the complete Python backend is approved, one coordinated release stops TypeScript backend processes and starts Python replacements. TypeScript remains available only as an emergency rollback artifact during stabilization. See [Python core full replacement and rollback](./PythonCoreStagedCutover.md).

## Architecture rules

### Bounded contexts

Create feature folders only when their vertical slice begins. Do not pre-create every future Nango service.

```text
nango-py/
  src/nango_py/
    <bounded-context>/
      transport/        # HTTP/event parsing and response mapping
      application/      # use cases and transaction orchestration
      domain/           # invariants, entities, value objects, domain errors
      infrastructure/   # SQLAlchemy repositories, crypto, external clients
  tests/
    unit/
    contract/
    integration/
    differential/
  tools/
    contracts/          # TypeScript fixture generation and normalization
```

Dependency direction:

```text
transport -> application -> domain
infrastructure -> application/domain ports
composition root -> transport + infrastructure
```

Rules:

- Routes only wire HTTP paths, dependencies, and handlers.
- Handlers validate transport shape, call one use case, and map results.
- Use cases own workflow and transaction boundaries.
- Domain code owns business invariants and imports no FastAPI, SQLAlchemy, or vendor SDK.
- Repository/gateway protocols use one async contract. Application code must not branch on concrete adapter types.
- Pydantic models own boundary serialization. Domain objects do not carry JSON aliases merely for transport compatibility.
- Each deployable service boundary gets its own composition root and health check. Do not combine server, persist, orchestrator, and jobs into one process for convenience.
- Typed domain/application errors map to stable transport errors. Do not infer behavior from exception message strings.

### Storage

- App DB and records DB use separate settings, engines, session factories, and health checks.
- Preserve `NANGO_DATABASE_*` and `RECORDS_DATABASE_*` behavior, schemas, search paths, UUID types, transaction semantics, and read replicas where required.
- Run current Knex migrations in integration-test setup before Python tests.
- SQLAlchemy mappings must preserve existing table defaults, indexes, encryption formats, cursor formats, locking, idempotency, and soft-delete behavior.
- Python does not add Alembic migrations until migration ownership is explicitly transferred from Knex.

### Security

- Authentication fails closed.
- Authorization scope checks match TypeScript wildcard semantics such as `environment:*`.
- Every protected route has explicit authentication and authorization tests.
- Secrets and record payloads preserve current encryption-at-rest formats.
- External input has request-size, collection-size, and semantic limits matching the authoritative TypeScript boundary.
- Errors must not expose credentials, tokens, decrypted payloads, stack traces, or internal SQL details.

### Contract evidence

Each migrated boundary needs fixtures covering:

- method, path, headers, query, and body
- response status, headers, and JSON casing
- authentication and scope outcomes
- validation and error envelopes
- storage side effects
- idempotency, concurrency, and retry behavior where relevant

Fixture source must identify the TypeScript test/controller/client that generated it. Normalize only documented nondeterministic values such as IDs and timestamps.

## Execution plan

### Phase 0 — Archive and compatibility harness

Goal: establish trustworthy evidence before production behavior.

- [x] **P0.1 Archive prototype** — move `nango-python/` to `python-core-spike/` without modifying archived implementation.
- [x] **P0.2 Bootstrap `nango-py/`** — package metadata, strict lint/type/test config, README, empty source package, and test layout only. No route behavior.
- [x] **P0.3 Confirm cutover strategy** — no production shadow/canary or traffic splitting; one full replacement with temporary TypeScript rollback artifacts.
- [ ] **P0.4 Build TypeScript fixture generator** — emit versioned request/response/error fixtures from authoritative TypeScript code.
- [x] **P0.5 Build migrated-Postgres test harness** — app DB and records DB, current Knex migrations, deterministic seed data, isolated test transactions.
- [ ] **P0.6 Add baseline CI gates** — Ruff, strict mypy, pytest, fixture drift, lock check, package build.

Checkpoint:

- Fixture generation runs from TypeScript.
- Python consumes fixtures without redefining expected output.
- Real app and records DB connections pass smoke tests.
- No public or internal production route exists yet.

### Phase 1 — First vertical slice: API-key auth plus integration read

Target boundary: `GET /integrations/:uniqueKey` for API-secret and customer-key authentication.

Why first: it exercises the highest-risk shared foundations—key hashing, UUID mapping, encryption, scope wildcard behavior, app DB access, provider resolution, public response formatting, and error envelopes—without adding writes or background execution.

Tasks:

- [x] **P1.1 Freeze contract fixtures** — success, missing auth, malformed auth, unknown key, missing scope, wildcard scope, unknown integration, credentials excluded, and credentials included.
- [x] **P1.2 Define auth domain/application contracts** — authenticated environment context, scopes, typed failures, and one async auth gateway.
- [x] **P1.3 Implement SQLAlchemy auth adapter** — current `api_secrets` and `customer_keys` schemas, UUID-safe mappings, hashing parity, secret decryption, and fail-closed behavior.
- [x] **P1.4 Implement integration read use case** — environment-scoped lookup, provider resolution, credential visibility policy, and typed not-found behavior.
- [x] **P1.5 Implement HTTP adapter** — exact TypeScript path, auth header handling, query validation, status codes, response shape, and error envelope.
- [ ] **P1.6 Verify real DB and differential parity** — migrated Postgres integration tests plus TypeScript/Python fixture comparison.
- [ ] **P1.7 Record differential evidence** — execute the same deterministic scenarios against TypeScript and Python, document accepted deltas, and add results to the cumulative replacement report.

Checkpoint:

- All Phase 0 gates remain green.
- No in-memory production fallback exists.
- Route behavior matches fixtures for success and failure paths.
- Differential report has no unexplained delta.
- Boundary remains offline until full replacement readiness.

### Phase 2 — Integration and provider reads

Progress:
- [x] Provider reads: `GET /providers` (list + `search` filter) and `GET /providers/:provider` with api-key auth, full catalog entry spread + `logo_url`, strict query validation. 8 e2e tests.
- [x] Integration list: `GET /integrations` with api-key auth, `list`/`list_credentials` scope, environment-scoped listing, deleted exclusion, strict query validation. 8 e2e tests.
- [ ] Connect-session authentication (needed for the Connect UI path and the integration-list `allowed_integrations` filter).
- [ ] Localization (Accept-Language provider overlays) — deferred; base catalog is returned today.

Remaining:
- Add integration list and provider read/list contracts.
- Add connect-session authentication only when provider routes require it for full parity.
- Preserve allowed-integration filtering, localization, credential scopes, display fields, and webhook include behavior.
- Add completed behavior to the cumulative offline differential and end-to-end suites; do not deploy the read family independently.

### Phase 3 — Connection reads

Progress:
- [x] Connection reads (api-key path): `GET /connections` (list with connectionId/integrationId/search/endUserId/endUserOrganizationId/tags filters, pagination, env scoping, deleted exclusion, end_user + active_logs + provider joins; key `connections`, no credentials) and `GET /connections/:id` (provider_config_key required + stringbool refresh params, integration lookup → `unknown_provider_config`, connection lookup → `not_found`, AES-GCM credential decryption, refresh_token stripping, read_credentials scope → full credentials else `{}`). 12 e2e tests + contract spec + 7 fixtures.
- [ ] Credential refresh / token refresh / github-app JWT / `invalid_credentials` error — deferred to Phase 5 (auth flows).
- [ ] Connect-session auth path (Connect UI) — deferred.
- [ ] Tag edge-case validation: `end_user_email` email check, duplicate-key-after-lowercase — deferred; functional core (max 10, key regex, lowercase normalize) implemented.

Remaining:
- Implement environment-scoped connection lookup/listing.
- Preserve encrypted credential mapping, credential visibility scopes, end users, tags, active errors, search, pagination, and exact public DTOs.
- Add real SQL tests for joined queries and UUID fields before marking the boundary complete.

### Phase 4 — Proxy

- Implement connection resolution, credential refresh, request construction, header policy, retries, redirects, decompression, and provider error mapping.
- Treat upstream URL handling, forwarded headers, secrets, and logs as security boundaries.
- Add SDK-driven differential tests and controlled upstream fixtures.

### Phase 5 — Connect sessions and authentication flows

- Implement durable connect sessions and compatible keystore tokens.
- Add reconnect, session read/delete, integration restrictions, plan checks, end-user/tags behavior, and Connect UI settings.
- Port OAuth and custom-auth families incrementally by auth mode; never introduce a generic auth abstraction before two proven modes require it.

### Phase 6 — Records and persist

- Use dedicated records DB configuration and current partitioned schemas.
- Preserve full-record wire shape, encryption, deterministic IDs, data hashes, advisory locking, batch upserts, merging cursors, counts, size accounting, checkpoints, and prune/delete semantics.
- Implement persist routes with exact paths and internal auth.
- Require concurrency and bidirectional TypeScript/Python storage interoperability tests before marking writes complete.

### Phase 7 — Orchestrator and scheduler

- Implement scheduler persistence against existing scheduler migrations.
- Preserve dequeue locking, group concurrency, retries, timeout expiry, heartbeat, recurring schedules, task outputs, and long polling.
- Keep orchestrator as a separate service boundary and composition root.

### Phase 8 — Jobs and Node runner integration

- Keep Node runner authoritative for JavaScript/TypeScript customer functions.
- Implement task preparation, deployed-code loading, runtime selection, start/abort/heartbeat/result callbacks, logs, checkpoints, and terminal-state idempotency.
- Prove action and sync execution end to end before adding other task types.

### Phase 9 — Webhooks, pubsub, usage, and deploy

Migrate these as independent slices:

- outgoing webhook payload/signature/retry behavior
- incoming provider webhook routing and forwarding
- pubsub envelope and production transports
- usage/metering consumers and stores, excluding billing providers
- backend deploy validation and compatible `nango.yaml` parsing

Each slice requires contract, integration, differential, failure-recovery, and cumulative full-system evidence. Slices are not deployed independently.

### Phase 10 — Full replacement and TypeScript retirement

- Pass every pre-cutover gate in `PythonCoreStagedCutover.md`.
- Rehearse the exact full replacement and rollback in a production-like non-production environment.
- Replace TypeScript backend processes with Python in one coordinated release window.
- Keep verified TypeScript artifacts deployable for an explicit stabilization window.
- Rehearse full rollback without rebuild or data migration.
- Apply `PythonCoreTypescriptRetirement.md` only after stabilization closes. Never retire SDK, UI, CLI, `nango-yaml`, runner SDK, or Node runner packages as part of backend cutover.

## Verification gates

Run from `nango-py/` once bootstrap exists:

```bash
uv lock --check
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

Additional mandatory gates by slice:

- TypeScript fixture generation and drift check
- migrated app/records/scheduler DB integration tests as applicable
- TypeScript/Python differential tests
- security tests for authentication, authorization, isolation, and secret exposure
- concurrency/idempotency tests for writes and task transitions
- cumulative TypeScript/Python differential report
- full-system end-to-end, load, failure-recovery, and storage-interoperability report
- non-production full replacement and rollback rehearsal report

## Definition of done for one boundary

A boundary is done only when:

- authoritative contract fixtures exist
- exact success and error behavior passes
- authentication and authorization fail closed
- real storage and encryption compatibility pass
- async/concurrency semantics pass where applicable
- no silent in-memory production fallback exists
- observability needed for support exists without adding out-of-scope telemetry
- differential and cumulative full-system evidence is reviewed
- full replacement and rollback are documented and rehearsed
- docs and ownership are current

## Salvage policy

Candidates may be copied only after independent parity tests prove them:

- provider catalog loading
- stable JSON and webhook signature helpers
- AES/PBKDF2 helpers
- small result/retry utilities
- common-v2 `nango.yaml` parser behavior
- focused state-machine tests

Do not copy these production structures from the spike:

- combined FastAPI composition root
- public API router/service implementation
- auth service and dependencies
- Postgres repository implementations
- persist/records implementation
- jobs processor/runtime wiring
- silent in-memory defaults

Archived tests may supply scenarios, but Python-owned expected values must not replace TypeScript-generated expectations.

## Risks and mitigations

- **Contract drift:** Generate fixtures from TypeScript and run them in CI.
- **False confidence from mocks:** Require migrated-schema DB tests before route completion.
- **Cross-tenant access:** Scope every query by authenticated environment and test hostile IDs.
- **Storage corruption:** Gate writes behind bidirectional interoperability tests, production-like backups, restore tests, and rollback rehearsal.
- **Mixed-language operational complexity:** Keep service boundaries explicit and Node runner unchanged.
- **Scope explosion:** One boundary at a time; billing, telemetry, and Python-native execution remain out of scope.
- **Premature abstractions:** Add ports only at real I/O boundaries; create bounded contexts and shared helpers only when current slices need them.

## Open decisions

- [ ] Stabilization-window duration and rollback triggers. Decide before the full replacement rehearsal.
- [ ] Target operational log schema. Decide before a boundary requiring durable logs.
- [ ] Ownership transfer for migrations. Knex remains authoritative until explicitly changed.
