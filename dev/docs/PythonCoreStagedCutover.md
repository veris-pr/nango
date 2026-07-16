# Python core full replacement and rollback

**Status:** Guardrail for the active `nango-py/` implementation. Execution order and readiness live in [Python core implementation plan](./PythonCoreImplementationPlan.md). `python-core-spike/` is archived and is not eligible for deployment.

## Replacement decision

Nango will not split, mirror, shadow, or canary production traffic between TypeScript and Python. Python is developed and verified offline until the complete replacement scope is ready. Cutover then replaces the TypeScript backend with Python in one coordinated release.

Incremental vertical slices remain the development method, not the deployment method. No Python slice receives production traffic before full-replacement readiness is approved.

TypeScript remains buildable and deployable as an emergency rollback artifact during a defined stabilization window. It serves no traffic after successful cutover unless rollback is triggered.

## Pre-cutover validation gates

Before scheduling replacement, all required backend boundaries must satisfy:

- TypeScript-generated contract fixtures pass against Python for public APIs, internal APIs, events, storage, webhooks, auth, errors, headers, and JSON casing.
- Full TypeScript/Python differential suite has no unexplained delta.
- Python integration tests pass against app, records, scheduler, keystore, and usage schemas produced by current authoritative migrations.
- Existing TypeScript SDKs, UIs, CLI, and Node runner pass end-to-end tests against Python.
- Cross-runtime storage tests prove TypeScript can read Python writes and Python can read TypeScript writes.
- Concurrency, idempotency, timeout, retry, recovery, and failure-injection tests pass.
- Production-scale load tests meet agreed latency, throughput, resource, and queue-backlog limits.
- Backup and restore are tested against a production-like dataset.
- Python deployment manifests, health checks, logs, alerts, runbooks, and ownership are complete.
- A non-production release rehearsal executes the exact replacement and rollback procedures.
- TypeScript rollback images and configuration are immutable, available, and verified.

Passing unit tests or package builds alone never authorizes cutover.

## Full replacement runbook

Use one planned maintenance/release window:

1. Announce the change window and freeze unrelated deploys and schema changes.
2. Confirm Python and rollback artifacts match the approved release candidates.
3. Confirm backups and rollback checkpoints are current.
4. Drain or pause work that cannot safely run in both implementations, including queued jobs and scheduled execution as defined by the operations runbook.
5. Stop TypeScript backend processes in dependency order.
6. Start Python backend processes using the same external contracts and approved storage.
7. Run blocking health, migration-state, queue, auth, API, persist, scheduler, jobs, Node runner, webhook, and usage smoke checks.
8. Resume paused work only after all blocking checks pass.
9. Record cutover time, artifact versions, DB checkpoint, operators, and smoke results.
10. Begin the stabilization window with enhanced operational monitoring.

No request-level traffic splitter, route proxy, or dual-serving mode is introduced.

## Rollback triggers

Rollback first when any agreed trigger occurs during stabilization:

- authentication or authorization bypass/failure
- data corruption, cross-tenant access, or incompatible writes
- repeated customer-facing contract failures
- queue/task loss, stuck execution, or invalid state transitions
- material error-rate, latency, or resource regression
- inability to diagnose customer-impacting failures with available logs

Investigation follows rollback unless continuing Python is demonstrably safer than reverting.

## Rollback to TypeScript

Rollback must not require a rebuild or data migration:

1. Pause new work and drain Python-owned work where safe.
2. Stop Python backend processes.
3. Start the verified TypeScript rollback artifacts with preserved configuration.
4. Run blocking TypeScript health and end-to-end smoke checks.
5. Confirm TypeScript reads data written since Python cutover.
6. Resume work and verify queues, schedules, runner callbacks, and webhooks recover.
7. Record incident window, trigger, affected data, artifact versions, and verification results.
8. Keep Python disabled until root cause and compatibility impact are reviewed.

If Python writes cannot be read safely by TypeScript, cutover readiness was not met. This is a release blocker, not a rollback-time migration task.

## Stabilization and retirement

The release owner must define stabilization duration before cutover. During that window:

- TypeScript artifacts remain buildable, deployable, and protected from incompatible changes.
- Python is the only active backend unless rollback occurs.
- Customer-impacting incidents use the rollback triggers above.
- Storage compatibility remains continuously verified.

After the window closes with owner approval, TypeScript backend retirement may proceed under [TypeScript core retirement readiness](./PythonCoreTypescriptRetirement.md). Retained TypeScript SDKs, UIs, CLI, `nango-yaml`, runner SDK, and Node runner are not retirement candidates.

## Explicit non-scope

- Billing migration and billing-provider events remain out of scope.
- New telemetry, tracing, metrics exporters, monitoring pipelines, and BigQuery ingestion remain out of scope.
- This document defines release requirements; deployment-manifest implementation is tracked by the implementation plan.

## Logs compatibility

Python must preserve customer-visible log contracts and provide operational logs needed to diagnose replacement and rollback. Prefer compatibility with current fields and error envelopes over introducing new telemetry concepts. Elasticsearch compatibility may remain necessary for existing deployments; new observability exporters are outside this migration.
