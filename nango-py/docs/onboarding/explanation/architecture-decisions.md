# Explanation: Architecture decisions

> Why the Nango Python port is structured the way it is.

## Decision 1: Python, not TypeScript

**Why port at all?** The TypeScript backend works. But the team chose Python for
strategic reasons:

- **Type system** — TypeScript's types are compile-time only. Python's type
  hints + strict mypy give runtime + compile-time checking, and the team
  values the stricter discipline.
- **Ecosystem** — Python's data ecosystem (pandas, async DB drivers, ML
  libraries) aligns with the platform's future direction.
- **Operational simplicity** — A single Python process is easier to operate
  than a mesh of TypeScript microservices.

**Why not rewrite from scratch?** The TypeScript code encodes years of
production-hardened behavior: auth edge cases, provider quirks, error
envelopes, encryption formats. Rewriting from scratch would lose all of that.

The solution: **contract-first port**. TypeScript stays as the source of
truth. Python reproduces the exact contracts. The TypeScript code remains as
a verified rollback artifact.

## Decision 2: DDD bounded contexts

**Why not a flat structure?** The TypeScript backend has a flat
controller-service-database structure. It works, but:

- Business logic is scattered across layers
- Auth concerns are mixed with business logic
- Services branch on adapter type (in-memory vs real DB)
- Hard to know what a change affects

The Python port uses DDD bounded contexts with four layers each. This
enforces:
- One responsibility per layer
- Clear dependency direction (inward only)
- Testability without I/O
- Fail-closed auth by construction

**The tradeoff:** More files, more boilerplate. A single TS controller might
become 4 Python files. This is deliberate — the structure makes contract
drift visible.

## Decision 3: Raw SQL, not ORM

**Why not SQLAlchemy ORM?** The Python port must produce exactly the same
SQL as the TypeScript Knex queries. ORM abstractions introduce translation
layers that can diverge:

- ORM might generate different JOIN syntax
- ORM might handle UUIDs differently
- ORM might add unexpected columns

Raw `sqlalchemy.text()` SQL is auditable against the TypeScript query builder
output. You can see exactly what hits the database.

**The tradeoff:** More manual SQL, no automatic relationship loading. But
the port's #1 risk is contract drift, and raw SQL minimizes it.

## Decision 4: Frozen dataclasses, not Pydantic

**Why not Pydantic for domain models?** Pydantic mixes validation,
serialization, and data shape. The domain layer should own invariants only:

- No JSON aliases (`by_alias`) in domain objects
- No validation logic in domain — that's transport's job
- No serialization concerns — frozen dataclasses are pure data

Pydantic is used where it belongs: transport request parsing (`contracts/`).

**The tradeoff:** No automatic JSON parsing in domain. But domain objects
are constructed by use cases, not deserialized from HTTP.

## Decision 5: Protocols, not ABCs

**Why `typing.Protocol`?** Structural typing: any class with matching methods
satisfies the Protocol. No inheritance required. This means:

- Infrastructure adapters don't need to import the Protocol
- Adapters can be tested in isolation
- The composition root injects concrete adapters
- Swap implementations without touching use case code

ABCs would force inheritance coupling. Protocols enable duck typing.

## Decision 6: No Alembic migrations

**Why?** Knex migrations (TypeScript) are authoritative. The Python port
operates against the same schema — it doesn't own it. Adding Alembic would
imply Python owns the schema, creating dual-migration risk.

Python uses raw SQL against the existing schema. When migration ownership is
explicitly transferred, Alembic can be added.

## Decision 7: No in-memory fallbacks

**Why?** The archived prototype had in-memory fallbacks for missing DB/keystore
config. This caused false confidence: tests passed because fakes always
worked, but production would fail silently.

The Python port fails closed:
- Missing DB config → startup fails
- Missing encryption key → startup fails
- Missing keystore → startup fails

No silent degradation. If something is misconfigured, you know immediately.

## Decision 8: Node runner stays TypeScript

**Why?** The runner executes customer JavaScript/TypeScript functions. Porting
it to Python would mean reimplementing a Node.js VM in Python — an enormous
effort with zero benefit.

The Python `jobs` service dispatches to the TypeScript runner via the runner
boundary protocol. The runner stays unchanged. The Python backend is
compatible with it.

## Decision 9: One coordinated cutover

**Why not gradual?** Both backends share the same database. Running both
against production data simultaneously risks write conflicts, encryption
races, and state divergence.

The port proves parity **before** cutover via fixtures, integration tests,
parity tests, and a rehearsal. The cutover is a process swap, not a data
migration. Risk is concentrated in one window with full attention.

## Decision 10: Contract-first, test-second

**Why not test-first?** Tests validate Python behavior. But if Python's
expected behavior is wrong, green tests give false confidence. The archived
prototype had green tests that validated wrong behavior through fakes.

The port starts with TypeScript contracts (fixtures), implements against
them, and verifies with parity tests. TypeScript defines correctness, not
Python tests.