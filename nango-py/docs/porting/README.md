# Nango Python Port — Documentation

> **Audience:** Engineers porting, extending, or verifying the Nango Python core.

This documentation set covers the TypeScript-to-Python backend port. It follows
the [Diátaxis](https://diataxis.fr) documentation framework — four quadrants,
each serving a different purpose.

## What this is

The Nango backend was originally written in TypeScript across several
`packages/` (server, orchestrator, scheduler, jobs, persist, records, keystore,
webhooks, pubsub). The Python port (`nango-py/`) replaces the backend core
while preserving every customer-visible and service-visible contract.

The TypeScript code remains the **source of truth** for contracts, types, and
behavior. When in doubt, review the TypeScript code, not just the Python tests.

## Documentation quadrants

```
                    ┌─────────────────────┬─────────────────────┐
                    │    Tutorials        │   How-to guides     │
                    │  (learning-oriented) │  (task-oriented)    │
 LEARNING / DOING   │                     │                     │
                    │  Start here if you   │  Come here if you   │
                    │  are new to the port │  have a specific    │
                    │  and want to learn   │  task to accomplish │
                    │  how it works        │                     │
                    ├─────────────────────┼─────────────────────┤
                    │    Reference        │   Explanation       │
                    │ (information-oriented)│ (understanding)   │
 UNDERSTANDING /    │                     │                     │
 REFERENCE          │  Come here for      │  Come here to       │
                    │  authoritative      │  understand why     │
                    │  technical facts    │  things are the     │
                    │                     │  way they are       │
                    └─────────────────────┴─────────────────────┘
```

### Tutorials — *Learning-oriented*
Guided lessons that walk you through a complete, real task end-to-end.

- [Your first route port](./tutorials/01-your-first-route-port.md) — Port a TypeScript route to Python, step by step
- [Verify parity with fixtures](./tutorials/02-verify-parity-with-fixtures.md) — Use TypeScript-generated fixtures to prove contract match
- [Add a new auth flow](./tutorials/03-add-a-new-auth-flow.md) — Port a new authentication mode

### How-to guides — *Task-oriented*
Solutions to specific problems you'll encounter during the port.

- [Add a new bounded context](./how-to/add-a-new-bounded-context.md) — Create the DDD folder structure for a new service boundary
- [Wire a new route into the composition root](./how-to/wire-a-new-route.md) — Register a new router in `server/app.py`
- [Fix a parity delta](./how-to/fix-a-parity-delta.md) — Diagnose and fix a TS-vs-Py response mismatch
- [Run the full test suite](./how-to/run-the-test-suite.md) — Execute unit, contract, integration, and parity tests

### Reference — *Information-oriented*
Authoritative technical descriptions you consult, not read end-to-end.

- [Route parity matrix](./reference/route-parity-matrix.md) — Full list of TS routes and their Python counterparts
- [Bounded context inventory](./reference/bounded-context-inventory.md) — All 17 bounded contexts and their layers
- [Error envelope reference](./reference/error-envelopes.md) — The three error envelope shapes and when to use each
- [Database schema reference](./reference/database-schema-reference.md) — Tables, search paths, and encryption formats
- [Contract inventory](./reference/contract-inventory.md) — API, internal service, pubsub, and webhook contracts

### Explanation — *Understanding-oriented*
Discussions that explain the "why" behind design decisions.

- [Why DDD boundaries](./explanation/why-ddd-boundaries.md) — Why the port uses domain-driven design layering
- [Why TypeScript is the source of truth](./explanation/why-typescript-is-source-of-truth.md) — The contract-first philosophy
- [The cutover strategy](./explanation/cutover-strategy.md) — Why one coordinated release, not gradual cutover
- [The differential harness](./explanation/the-differential-harness.md) — How dual-backend testing proves parity