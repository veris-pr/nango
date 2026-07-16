# Explanation: Why TypeScript is the source of truth

> Why the Python port treats the TypeScript code as the authoritative
> reference, not just "another implementation."

## The contract-first philosophy

The TypeScript backend is in production. Customer SDKs (`node-client`,
`frontend`, `connect-ui`) consume its API shapes. The CLI sends deploy
payloads shaped by TypeScript types. Internal services (orchestrator,
scheduler, jobs, runner, persist) exchange messages with contracts defined
in `@nangohq/types`.

If the Python port produces a different response shape, a different error
code, or a different error envelope, customer integrations break — silently,
in production, at cutover time.

The only way to prevent this is to treat TypeScript as the source of truth
for every contract: API shapes, error envelopes, database schemas,
encryption formats, auth scope semantics, and internal service RPCs.

## What "source of truth" means in practice

### 1. Read the TypeScript before writing Python

Every ported endpoint starts by reading the TypeScript controller:

```
packages/server/lib/controllers/<area>/<controller>.ts
```

Extract: path, method, auth, validation, response shape, error codes, side
effects. Then write Python that produces the same behavior.

### 2. Generate fixtures from TypeScript

Contract fixtures are generated from TypeScript behavior, not handwritten:

```
tools/crypto_vectors.gen.mjs   # Node script that produces test vectors
tests/contract/fixtures/        # JSON consumed by Python tests
```

Python tests consume these fixtures. Python never defines the expected
output — TypeScript does.

### 3. Run parity tests against both backends

The parity harness runs the same request against both backends live and
compares responses. This catches drift that fixtures miss (e.g., dynamic
behavior, database state, timing).

### 4. When in doubt, read TypeScript

From the user's stated philosophy:

> "TypeScript is a strictly typed, statically typed systems programming
> language whose contracts make porting to Python easier — whenever in
> doubt, review the TypeScript code rather than just running tests."

If a Python test passes but you're unsure whether it matches TypeScript,
don't trust the test. Read the TypeScript controller and verify the
behavior matches.

## Why not "just make the tests pass"

The archived `python-core-spike/` prototype had green tests — but they
validated Python-owned behavior through in-memory fakes, not TypeScript
contracts. Review found:

- Fail-open authentication (tests passed because fakes always authenticated)
- Missing authorization scopes (tests passed because fakes granted all scopes)
- Incompatible persist contracts (tests passed because they tested Python's
  own format, not TypeScript's)
- Broken real-Postgres mappings (tests passed because they used in-memory
  repos, not real DB)

Green tests are necessary but not sufficient. Parity with TypeScript is the
actual requirement.

## What stays in TypeScript

The port replaces the **backend core** only. These remain TypeScript:

- `packages/node-client` — server-side SDK
- `packages/frontend` — browser SDK
- `packages/connect-ui` — Connect UI React app
- `packages/cli` — CLI tool
- `packages/nango-yaml` — nango.yaml parser (CLI)
- `packages/runner` — Node runner for customer JS/TS functions
- `packages/runner-sdk` — SDK injected into customer functions

The Python backend must be **compatible** with all of these. They are not
ported; they are preserved.

## The contract inventory

The full contract inventory is frozen in
`dev/docs/PythonCoreContractInventory.md`. It covers:

1. Public API contracts (all endpoint families)
2. CLI deploy and config contracts (nango.yaml, deploy payloads)
3. Internal service contracts (orchestrator, scheduler, jobs, runner, persist)
4. Pubsub event contracts (envelope shape, event types)
5. Database and storage contracts (app DB, records DB, scheduler DB, keystore)
6. Webhook payload and signature contracts

This inventory is the specification. The Python port implements against it.