# Python core staged cutover and rollback

This document defines a safe foundation for moving Nango traffic from the existing TypeScript services to the Python core one service or route family at a time. It is not a production deployment plan and does not add live routing, proxying, telemetry, billing, or deployment manifest changes.

For the separate checklist that must be satisfied before any TypeScript core service code is deleted, see [TypeScript core retirement readiness](./PythonCoreTypescriptRetirement.md).

## Cutover model

Use a strangler pattern: keep TypeScript as the source of truth, then evaluate Python compatibility by route family before any route becomes active.

1. **Service boundary selection**: choose one boundary such as health, orchestrator, persist, or a public API route family. Do not mix unrelated boundaries in the same cutover.
2. **Contract parity**: confirm request and response DTOs, auth headers, status codes, error envelopes, and JSON field casing match the TypeScript service.
3. **Shadow validation**: send representative non-customer-impacting requests or replay fixtures to Python while TypeScript still serves production traffic.
4. **Canary validation**: allow a small, explicitly configured route family or environment to use Python after the shadow checks pass.
5. **Active cutover**: route the selected boundary to Python only after validation gates are green and rollback has been rehearsed.

Do not introduce a generic proxy layer as part of this foundation. Any future live router should be reviewed separately with service-specific ownership and rollback criteria.

## Cutover mode flag

The Python core exposes its requested cutover mode through `GET /health` so deployment and smoke-check tooling can verify intent without scraping process configuration.

| Environment variable        | Allowed values                           | Default    | Meaning                                                             |
| --------------------------- | ---------------------------------------- | ---------- | ------------------------------------------------------------------- |
| `NANGO_PYTHON_CUTOVER_MODE` | `disabled`, `shadow`, `canary`, `active` | `disabled` | Declares the process cutover intent for status and validation only. |

Mode semantics:

- `disabled`: Python is available for local/dev validation only. TypeScript services remain authoritative.
- `shadow`: Python may receive fixture or mirrored validation traffic, but responses must not affect customers.
- `canary`: a narrowly scoped service or route family may be directed to Python by external routing configuration.
- `active`: the selected route family is expected to be served by Python, with rollback ready.

The mode is metadata only. It does not perform live routing, proxying, traffic splitting, or failover.

## Validation gates

Before moving a boundary to the next mode, validate:

- `GET /health` returns `status: "ok"`, the expected `service`, and the expected `cutover_mode`.
- Python contract fixtures pass: `python scripts/check_contract_fixtures.py`.
- Python quality checks pass from `nango-python/server`: `python -m ruff check .`, `python -m mypy`, and `python -m pytest`.
- Route-specific fixture or smoke tests confirm TypeScript-compatible status codes, error shapes, headers, auth behavior, and JSON casing.
- TypeScript remains available for the same route family until active cutover is complete and rollback is no longer needed.

## Rollback to TypeScript

Rollback should be route-by-route and should not require rebuilding Python.

1. Change external routing for the affected service or route family back to the TypeScript service.
2. Set `NANGO_PYTHON_CUTOVER_MODE=disabled` or `shadow` for the Python process at the next safe restart or config rollout.
3. Verify the TypeScript health endpoint and route-specific smoke checks pass.
4. Verify Python `GET /health` reports the downgraded mode if the process remains deployed.
5. Keep Python available for fixture replay or investigation, but do not let Python responses affect customers while rollback is active.

## Explicit non-scope

- Billing migration and provider billing events are out of scope.
- Telemetry, tracing, metrics exporters, monitoring pipelines, and BigQuery ingestion are out of scope.
- This document does not modify production deployment manifests.

## Logs compatibility note

Python route implementations should preserve existing customer-visible log contracts where a migrated boundary already emits logs. Prefer compatibility with current operational log fields and error envelopes over adding new telemetry concepts. Elasticsearch compatibility may be needed for existing deployments, but adding new observability exporters is outside this staged cutover foundation.
