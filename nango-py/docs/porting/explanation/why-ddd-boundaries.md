# Explanation: Why DDD boundaries

> Why the Python port uses domain-driven design layering instead of a flat
> service/controller structure.

## The problem

The TypeScript backend has a flat structure: controllers call services,
services call database utilities, everything can import everything. This works
when the codebase is small, but the Nango backend has 50+ packages with
overlapping concerns, circular dependencies, and business logic scattered
across transport, service, and database layers.

When porting to a new language, a flat structure amplifies risk:
- Auth logic mixed with business logic → hard to audit fail-closed behavior
- Service functions branch on adapter type → hard to test without real DB
- Business rules scattered across layers → easy to miss during port
- No clear ownership → hard to know what a change affects

## The solution: DDD bounded contexts

The Python port uses domain-driven design with four layers per bounded
context:

```
transport/        ← HTTP parsing, validation, response mapping
application/      ← use cases, transaction orchestration, gateway Protocols
domain/           ← invariants, entities, value objects, domain errors
infrastructure/   ← SQLAlchemy repositories, crypto, external clients
```

### Dependency direction

```
transport  ──→  application  ──→  domain
infrastructure  ──→  application / domain ports
composition root  ──→  transport + infrastructure
```

The dependency direction is strictly enforced:
- `domain/` imports nothing from transport, infrastructure, or vendor libs
- `application/` imports from `domain/` and defines Protocols, not concrete adapters
- `infrastructure/` implements Protocols, imports from `domain/`
- `transport/` imports from `application/` and `domain/`

### Why this matters for a port

1. **Contract clarity** — Each layer has a clear responsibility. When a
   TypeScript controller does X, you know exactly which Python layer should
   do X. No guessing where to put logic.

2. **Testability** — Domain logic has no I/O dependencies, so unit tests are
   fast and deterministic. Application Protocols enable mock-free testing
   of use cases. Infrastructure tests hit real Postgres.

3. **Fail-closed security** — Auth logic lives in the `auth` context, separate
   from business logic. Scope checks are explicit use case calls, not buried
   in middleware. You can audit every auth path by reading one folder.

4. **No silent fallbacks** — The composition root explicitly wires concrete
   adapters. There's no "if no DB, use in-memory" fallback. Missing config
   fails startup, not silently degrades.

5. **Parity by construction** — Each TypeScript endpoint maps to one Python
   route → one use case → one gateway call. The structure itself enforces
   that every concern is covered.

## Why frozen dataclasses, not Pydantic

The domain layer uses frozen dataclasses, not Pydantic models:

- **No serialization concerns** — Domain objects don't carry JSON aliases
  or `by_alias` flags. Transport serialization is a separate concern.
- **No validation mixing** — Validation happens at the transport boundary
  (Pydantic for request parsing, manual checks for query/headers). Domain
  enforces invariants, not wire format.
- **Immutability** — Frozen dataclasses prevent accidental mutation of
  domain state. Every operation returns a new instance.

## Why Protocols, not ABCs

Gateway protocols use `typing.Protocol`, not `abc.ABC`:

- **Structural typing** — Any class with matching methods satisfies the
  Protocol. No inheritance required.
- **No coupling** — Infrastructure adapters don't need to import the
  Protocol to satisfy it. The adapter can be tested in isolation.
- **DI-friendly** — The composition root injects concrete adapters. Use
  cases accept the Protocol. Swap implementations without touching use case
  code.

## Why raw SQL, not ORM

Infrastructure uses `sqlalchemy.text()` with raw SQL, not ORM mappings:

- **Exact schema match** — The Python port must produce exactly the same
  SQL as the TypeScript Knex queries. ORM abstractions introduce translation
  layers that can diverge.
- **No migration ownership** — Knex migrations remain authoritative. ORM
  mappings would imply Python owns the schema, which it doesn't (yet).
- **Auditability** — Raw SQL is easier to compare against the TypeScript
  query builder output. You can see exactly what hits the database.

## The tradeoff

DDD boundaries add more files and more boilerplate. A single TypeScript
controller might become 4 Python files (route + use case + domain + gateway).

This is deliberate. The port's #1 risk is contract drift, not lines of code.
The structure makes drift visible — if a Python response doesn't match
TypeScript, you know exactly which layer to inspect.