# RFC: Python-native Nango Functions runtime

## Status and recommendation

This is an evaluation document only. It does not implement a Python function runtime and does not change the current TypeScript/JavaScript execution path.

**Recommendation for now:** keep the Node runner during the Python core migration. Existing TypeScript customer functions, the CLI bundling flow, `runner-sdk`, and the Node runner must remain compatible while backend services move toward Python. Revisit a Python-native functions runtime only after the backend cutover has proven contract parity, rollback, and operational ownership for core services.

Billing and new telemetry work are out of scope for this RFC.

Related migration plan and guardrails:

- [Python core implementation plan](./PythonCoreImplementationPlan.md)
- [Python core full replacement and rollback](./PythonCoreStagedCutover.md)
- [TypeScript core retirement readiness](./PythonCoreTypescriptRetirement.md)
- [Python core contract inventory](./PythonCoreContractInventory.md)

## Problem statement

The active `nango-py/` implementation will move selected backend service responsibilities from TypeScript to Python. Customer function execution is a different boundary: today, customer integrations are authored, bundled, and executed as TypeScript/JavaScript with a Node runner and a JavaScript `nango` runtime SDK surface.

A future Python-native function runtime could let customers write Nango Functions in Python and could align function execution with a Python backend. However, that runtime would create a new customer-facing contract across deploy artifacts, SDK behavior, persistence, logs, lifecycle control, dependency isolation, and error semantics. It should be treated as a product/runtime design, not as an incidental part of the backend core migration.

## Non-goals

- Do not replace or modify the current Node runner as part of the Python core migration.
- Do not migrate existing TypeScript/JavaScript customer functions to Python automatically.
- Do not change CLI deploy behavior for existing TypeScript/JavaScript functions.
- Do not change `@nangohq/runner-sdk` compatibility for existing functions.
- Do not define billing, metering pricing, or new telemetry/tracing pipelines.
- Do not remove TypeScript runtime packages, Docker targets, or build paths.
- Do not implement a Python function runtime in this RFC.

## Current runner model

The current model has four distinct responsibilities:

1. **CLI bundles TypeScript/JavaScript**: deploy tooling parses project configuration, builds customer function code, and uploads deploy artifacts that the backend can validate and schedule.
2. **Jobs coordinates execution**: `jobs` dequeues tasks from orchestrator/scheduler, prepares execution context, selects the runtime path, starts the runner, receives final results, records side effects, and updates task state.
3. **Runner executes customer code**: the Node runner receives code plus `NangoProps`, executes the bundled CommonJS-wrapped function in Node, sends heartbeats, supports abort, and returns output or errors to jobs.
4. **Runner SDK provides `nango`**: `runner-sdk` is exposed inside customer functions as the `nango` object, including records, checkpoints, logging, proxy/helper calls, and persistence-related APIs.

This separation should remain intact while Python core backend work proceeds. A Python-native runtime would need to plug into the same coordination and persistence responsibilities without regressing the Node path.

## Options

### Option A: Keep TypeScript/JavaScript-only functions

Continue supporting only the current Node runner for Nango Functions while Python backend services are migrated.

**Pros**

- Lowest risk for existing customers.
- Keeps deploy artifacts, CLI behavior, runner-sdk semantics, and operational runbooks stable.
- Lets Python core migration focus on backend service contract parity.

**Cons**

- Does not unlock Python-authored customer functions.
- Keeps a mixed-language platform even after Python owns more backend services.

**Fit now:** recommended during backend migration.

### Option B: Add Python as a second runtime

Add a Python function runtime alongside the Node runner. Runtime selection would be explicit per deployed function or integration artifact.

**Pros**

- Preserves existing TypeScript/JavaScript compatibility.
- Enables incremental prototype and beta rollout for Python-authored functions.
- Allows runtime-specific dependency isolation and SDK design without forcing a rewrite.

**Cons**

- Requires a new deploy artifact contract and Python runtime SDK.
- Doubles runtime validation, sandboxing, dependency management, and support paths.
- Requires precise compatibility for records, logs, abort, heartbeat, result, and error behavior.

**Fit later:** likely first viable path after Python core cutover proves backend contracts.

### Option C: Replace the runner later

Eventually replace the current runner architecture with a new runtime host that may support Python first or multiple languages behind one abstraction.

**Pros**

- Could simplify runtime hosting after proven multi-runtime requirements are known.
- Could consolidate lifecycle handling, isolation, and deployment controls.

**Cons**

- Highest regression risk for existing TypeScript/JavaScript customer functions.
- Requires proving parity for Node execution and runner-sdk behavior before replacement.
- Couples customer runtime migration to infrastructure changes.

**Fit now:** not recommended initially. Consider only after a second runtime has proven contracts and adoption.

## Required contracts for any Python runtime

A Python-native runtime cannot be accepted until these contracts are explicit, versioned, and covered by fixtures or compatibility tests.

### Deploy artifact shape

- How the CLI identifies a Python function runtime versus the existing TS/JS runtime.
- Artifact contents: source files, entrypoint, function type, runtime version, lockfile or dependency manifest, generated metadata, and checksums.
- Backward-compatible server validation for existing TS/JS artifacts.
- Storage and retrieval format used by jobs/runner without assuming Node-only bundles.
- Versioning and rollback behavior for artifact schema changes.

### Runtime SDK

- Python equivalent of the injected `nango` object.
- API parity decisions for records, checkpoints, logging, proxy, secret/config access, helper calls, and connection metadata.
- Async model and cancellation semantics.
- Stable error types and serialization into current job result envelopes.
- SDK version compatibility declared in deploy artifacts.

### Records, logs, and persist calls

- Record batch write semantics, merge behavior, cursor/checkpoint updates, and idempotency expectations.
- Log shape compatibility for customer-visible logs and operational debugging.
- Persist service authentication, environment scoping, connection/sync/job path construction, retries, and error mapping.
- Compatibility fixtures proving Python SDK calls produce equivalent persisted effects where the same API exists in Node.

### Heartbeats and lifecycle control

- Heartbeat interval, timeout behavior, retry/backoff, and task state transitions.
- Abort signal delivery from jobs to the Python runtime.
- Cleanup guarantees when a function is aborted, times out, crashes, or exits normally.
- `notifyWhenIdle` or equivalent capacity/idle semantics if jobs continues depending on runner-level lifecycle signals.

### Results and errors

- Result envelope for actions, syncs, webhooks, and on-event functions.
- Exception capture, stack trace redaction, customer-facing error messages, and internal error classification.
- Mapping to jobs callback fields without requiring TS/JS-only assumptions.
- Deterministic behavior for partial record writes plus final failure.

### Dependency isolation

- Python dependency declaration format and lockfile policy.
- Per-deploy or per-environment virtual environment/container isolation.
- Native package build policy, allowed system libraries, cache invalidation, and vulnerability update process.
- Resource limits for CPU, memory, filesystem, network, and execution time.
- Safe cleanup of dependencies and temporary execution state between tenants.

## Compatibility plan

Existing TypeScript/JavaScript functions must not regress.

- Keep the Node runner as the default and authoritative runtime for existing deploy artifacts.
- Require explicit runtime metadata before jobs can route any function to a Python runtime.
- Preserve current CLI bundling behavior for TS/JS projects; Python deploy support should be additive.
- Keep `packages/runner` and `packages/runner-sdk` buildable, deployable, and smoke-tested throughout backend migration.
- Add fixture coverage that runs existing TS/JS function artifacts through the Node path after any runtime-selection changes.
- Keep result, heartbeat, abort, log, and persist contracts backward compatible for jobs and orchestrator.
- Avoid shared abstractions that force Node behavior changes before Python runtime behavior is proven.

## Proposed prototype milestones

### Milestone 0: Contract inventory

Acceptance criteria:

- Deploy artifact schema proposal distinguishes TS/JS and Python without changing existing artifacts.
- Runtime SDK API matrix identifies required parity, Python-specific differences, and unsupported APIs.
- Jobs-to-runner lifecycle contract covers start, heartbeat, abort, result, and failure cases.
- Persist/logs fixture plan is reviewed before implementation begins.

### Milestone 1: Local-only Python runtime spike

Acceptance criteria:

- Runs a single Python action locally from an explicit Python artifact fixture.
- Provides a minimal Python `nango` SDK stub for logs and result return only.
- Does not integrate with production deploys, scheduling, or existing Node runner paths.
- Documents unsupported APIs and known gaps.

### Milestone 2: Persist and lifecycle prototype

Acceptance criteria:

- Supports records/checkpoints/log calls against a non-production persist environment.
- Sends heartbeats and handles abort in a controlled test harness.
- Produces jobs-compatible success and failure envelopes.
- Demonstrates dependency isolation for at least one third-party Python package.

### Milestone 3: Compatibility gate for dual runtime beta

Acceptance criteria:

- Existing TS/JS function fixture suite passes unchanged through the Node runner.
- Python runtime fixtures pass for actions and one sync scenario.
- Runtime selection is explicit and defaults to Node for all existing artifacts.
- Rollback from Python runtime to no Python execution path is documented and tested.
- Operational runbook covers logs, stuck tasks, dependency failures, aborts, and cleanup.

## Decision for the current migration phase

Keep the Node runner during the Python core migration. Do not include Python-native function execution in backend cutover scope. Revisit this RFC after backend cutover when Python core service boundaries have proven contract parity, TypeScript rollback remains understood, and the team is ready to evaluate a second customer-facing runtime independently.
