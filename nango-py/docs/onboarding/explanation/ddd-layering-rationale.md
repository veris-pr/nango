# Explanation: DDD layering rationale

> Why each bounded context has four layers, and what each layer is
> responsible for (and not responsible for).

## The four layers

```
┌──────────────────────────────────────────────────────┐
│  Transport                                          │
│  HTTP parsing, validation, response serialization   │
│  May import: FastAPI, Pydantic                      │
└────────────────────┬─────────────────────────────────┘
                     │ depends on (inward)
┌────────────────────▼─────────────────────────────────┐
│  Application                                        │
│  Use cases, gateway Protocols, scope checks         │
│  May import: domain only                            │
└────────────────────┬─────────────────────────────────┘
                     │ depends on (inward)
┌────────────────────▼─────────────────────────────────┐
│  Domain                                             │
│  Frozen dataclasses, invariants, typed errors       │
│  May import: nothing (no vendor libs)               │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│  Infrastructure (parallel, not above)               │
│  SQLAlchemy repos, crypto, external HTTP clients     │
│  Implements: application Protocols                  │
│  May import: domain, SQLAlchemy, httpx, cryptography │
└──────────────────────────────────────────────────────┘
```

The dependency direction is strictly **inward**. Outer layers depend on inner
layers. Inner layers never depend on outer layers.

## Why four layers (not three)

Traditional DDD uses three layers: presentation, domain, infrastructure. The
Nango port splits "presentation" into **transport** and **application**:

- **Transport** owns HTTP concerns: parsing, validation, serialization
- **Application** owns business workflow: use cases, scope checks, transaction
  orchestration

Why split them?

### Transport does too much if combined

In the TypeScript backend, controllers do: HTTP parsing, validation,
business logic, response formatting. This makes them hard to test (need
HTTP context) and hard to audit (business logic mixed with transport).

Splitting transport from application means:
- Transport is thin: parse → validate → call use case → serialize
- Application is testable: no HTTP, no FastAPI, just pure async functions
- Business logic lives in use cases, not route handlers

### Application is the seam

The application layer defines Protocols (gateway interfaces). This is the
seam where infrastructure plugs in. If you want to swap PostgreSQL for
something else, you implement the Protocol — no use case changes.

## What each layer owns

### Domain

**Owns:**
- Data shapes (frozen dataclasses)
- Business invariants (constructors, `__post_init__`)
- Typed errors (`ApiError` subclasses)
- Pure functions (no I/O)

**Does NOT own:**
- HTTP parsing
- Database queries
- Serialization to JSON
- Validation of external input
- Any vendor library import

**Test:** Unit tests, no mocks needed.

### Application

**Owns:**
- Use cases (workflow orchestration)
- Gateway Protocols (I/O ports)
- Scope checks (authorization)
- Transaction boundaries
- Request/response domain objects

**Does NOT own:**
- HTTP parsing
- Database queries (delegates to gateway)
- Response serialization (delegates to transport)
- Business invariants (delegates to domain)

**Test:** Unit tests with mock gateways, or integration tests with real
gateways.

### Infrastructure

**Owns:**
- Concrete gateway implementations
- SQL queries
- External HTTP calls
- Encryption/decryption
- File I/O

**Does NOT own:**
- Business logic (delegates to domain)
- Scope checks (that's application's job)
- Response shaping (that's transport's job)

**Test:** Integration tests against real Postgres.

### Transport

**Owns:**
- Route definitions (path, method, auth dependency)
- Request parsing (query, path, body, headers)
- Input validation (Pydantic, regex, enum checks)
- Response serialization (domain → JSON dict with camelCase keys)
- Error-to-HTTP-status mapping

**Does NOT own:**
- Business logic (calls use case)
- Database queries (use case does that)
- Scope checks (use case does that)

**Test:** Integration tests via httpx AsyncClient.

## The NOT_SET pattern

One subtlety: TypeScript distinguishes between `null` and "key omitted." Python
domain uses `NOT_SET` for omission:

```python
class _NotSet:
    __slots__ = ()

NOT_SET: _NotSet = _NotSet()

@dataclass(frozen=True)
class PublicIntegrationView:
    webhook_url: str | None | _NotSet = NOT_SET
```

In serialization:
- `NOT_SET` → key omitted from JSON
- `None` → key included as `null`
- `"value"` → key included as `"value"`

This matches TypeScript's conditional key assignment:
```typescript
if (include.webhook) { response.webhook_url = ... }
```

## Why Protocols (not ABCs)

Gateway ports use `typing.Protocol`:

```python
class IntegrationRepository(Protocol):
    async def get_by_unique_key(self, *, environment_id: int, unique_key: str) -> Integration | None: ...
```

Benefits:
- **Structural typing** — any class with matching methods satisfies it
- **No inheritance** — infrastructure doesn't need to import the Protocol
- **Testability** — mock objects automatically satisfy the Protocol
- **DI** — composition root injects concrete adapters

## The composition root

`server/app.py` is the **only** place that knows about concrete
implementations. It:

1. Creates infrastructure adapters (SQLAlchemy repos, YAML catalog)
2. Creates use cases, injecting adapters via Protocol
3. Creates routers, injecting use cases
4. Registers routers + exception handler

No other file imports a concrete infrastructure class. This means:
- Swap any adapter without touching use cases or transport
- Test use cases with mock gateways (Protocol-compatible)
- Add new infrastructure implementations without touching application code

## Summary

| Layer | Imports | Owns | Tests |
|-------|---------|------|-------|
| Domain | nothing | data shapes, invariants, errors | unit (no mocks) |
| Application | domain | use cases, Protocols, scope checks | unit (mock gateways) |
| Infrastructure | domain, SQLAlchemy, httpx | SQL, crypto, external calls | integration (real DB) |
| Transport | FastAPI, application | routes, parsing, serialization | integration (httpx) |
| Composition root | all | wiring | smoke |