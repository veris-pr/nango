# TypeScript core retirement readiness

This document defines the readiness checklist for retiring TypeScript core service modules after the Python core reaches proven production parity. It is intentionally a guardrail, not an execution record.

No TypeScript service, package, Docker target, deployment reference, or root script is removed by the current Python core foundation work. The current foundation only establishes incremental Python compatibility surfaces; it does not prove production parity.

## Preconditions before deletion

Do not delete any TypeScript core module until all of the following are true for the specific service boundary:

1. Python serves the same production traffic for that boundary in `active` mode for the agreed rollback window.
2. TypeScript remains deployable and routable during the rollback window.
3. Contract parity is proven for public APIs, internal service APIs, storage behavior, auth, error envelopes, headers, status codes, JSON casing, webhook signatures, and queue/event payloads.
4. Shadow and canary runs have been reviewed by the owning team, including failure cases and operational runbooks.
5. Deployment, local development, CI, and release owners agree that no retained TypeScript package depends on the module being removed.
6. Rollback has been rehearsed by routing traffic back to TypeScript without a rebuild or data migration.

Deletion should be proposed service-by-service. Avoid bulk removals across unrelated boundaries.

## Eventual retirement candidates

The following TypeScript core areas may become eligible for retirement only after Python owns the same runtime responsibility and all preconditions above are met:

| Area                                          | Current TypeScript location                                                       | Retirement condition                                                                                  |
| --------------------------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Public API server routes                      | `packages/server`                                                                 | Python owns the selected route family with matching SDK-visible contracts.                            |
| Orchestration and scheduling coordination     | `packages/orchestrator`, `packages/scheduler`, `packages/jobs` coordination paths | Python owns task creation, scheduling, lifecycle updates, retries, heartbeats, and failure semantics. |
| Persistence and record APIs                   | `packages/persist`, `packages/records` server-side paths                          | Python owns record writes, merges, cursor behavior, and database compatibility.                       |
| Webhook delivery and provider webhook routing | `packages/webhooks`, relevant `packages/server/lib/webhook/**` paths              | Python owns payload shapes, stable stringification/signatures, retry behavior, and routing semantics. |
| Core pub/sub adapters and event handling      | `packages/pubsub` server-side usage                                               | Python owns equivalent event envelopes, idempotency behavior, and transport integration.              |
| Backend key and storage access                | `packages/keystore`, `packages/database` server-side usage                        | Python owns compatible migrations, encryption formats, and data access behavior.                      |
| Backend deploy validation                     | `packages/server` deploy controllers and Python-compatible YAML validation        | Python validates the same deploy payloads without replacing the CLI parser.                           |

Some shared TypeScript libraries may survive longer than the service that originally used them. Remove them only when no retained package imports them and no release artifact depends on them.

## TypeScript packages that must remain

The Python core migration must not remove TypeScript packages that are SDKs, UIs, CLIs, or JavaScript execution runtimes:

- `packages/webapp`
- `packages/connect-ui`
- `packages/frontend`
- `packages/node-client`
- `packages/cli`
- `packages/runner-sdk`
- `packages/runner`
- `packages/nango-yaml` for CLI parsing of `nango.yaml`

The runner stack must remain TypeScript/Node because it executes customer JavaScript/TypeScript functions and exposes the runner SDK bridge. The CLI must continue using the TypeScript `nango-yaml` parser unless a separate CLI migration is explicitly designed and shipped.

Billing and telemetry are out of scope for this retirement plan.

## Required parity evidence

Attach the evidence to the removal PR or linked design review:

- Contract fixture results for each retired route family or service boundary.
- Shadow comparison report showing request/response equivalence and accepted deltas.
- Canary report with traffic scope, duration, incidents, and rollback result.
- Database compatibility review covering migrations, defaults, indexes, serialization, encryption, and cursor formats.
- Queue/event compatibility review covering payload schemas, idempotency keys, ordering assumptions, retries, and dead-letter behavior.
- SDK and UI smoke results proving retained packages still work against Python-owned boundaries.
- Operations sign-off covering health checks, deployment steps, logs needed for support, and rollback ownership.

Keep the TypeScript implementation available until this evidence has been reviewed and the rollback window has elapsed.

## Rollback window

Each service boundary needs an explicit rollback window before deletion. During that window:

1. TypeScript images and configuration remain buildable and deployable.
2. Routing can be switched back to TypeScript without code changes.
3. Data written by Python remains readable by TypeScript or has a documented compatibility exception.
4. Customer-impacting incidents trigger rollback first, investigation second.
5. The end of the window is recorded with owner approval.

Only after the window closes should a follow-up PR remove TypeScript code for that boundary.

## Removal checklist

Use this checklist in the future deletion PR. It is not performed by the current foundation PR/session.

### Package references

- Remove retired package entries from workspace metadata and lockfiles.
- Remove `dependencies`, `devDependencies`, and local `file:../...` references from retained packages.
- Remove imports, package aliases, generated API clients, and shared barrel exports that point at retired packages.
- Confirm retained packages listed above still install, build, and publish as applicable.

### Docker and deployment references

- Remove retired service Docker targets, compose services, health checks, environment variables, and image tags.
- Remove deployment manifests, GitHub Actions jobs, release scripts, and process-manager entries for the retired service.
- Verify no production, staging, self-hosted, or local-development path still references the retired process.

### Root scripts and developer workflows

- Remove root `package.json` scripts that build, lint, test, start, or publish the retired service.
- Remove service-specific local setup docs and replace them with Python workflow links.
- Update onboarding docs so new contributors no longer start the retired TypeScript process.

### TypeScript project references

- Remove retired package references from `tsconfig.json`, `tsconfig.build.json`, package `tsconfig*.json` files, and any build-order metadata.
- Remove generated `.tsbuildinfo` assumptions if they reference retired projects.
- Run the existing TypeScript build/lint checks for retained packages.

### Compatibility cleanup

- Remove temporary shadow/canary compatibility shims only after Python is the sole owner.
- Remove duplicated fixtures only after equivalent Python contract tests remain.
- Update architecture docs, service diagrams, and runbooks to show the Python-owned boundary.

## Current status

Current Python core work is a foundation for incremental validation. It does not delete TypeScript code and does not claim production parity. Treat every TypeScript core module as retained until a later, evidence-backed removal PR satisfies this checklist.
