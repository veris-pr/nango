# Python tests

## nango.yaml parser parity

`tests/fixtures/nango_yaml` contains representative v2 `nango.yaml` configs used by the
Python backend parser. The parser aims for TypeScript `packages/nango-yaml` shape parity for
deploy/config processing, but this incremental port intentionally covers only common backend
needs: integrations, syncs, actions, on-events, endpoints, scopes, input/output, model fields,
arrays, unions, model references, and simple inheritance.

Unsupported or intentionally shallow areas for now:

- v1 `nango.yaml` configs.
- Full JavaScript/TypeScript type grammar and code-generation behavior.
- CLI-only schema edge cases and feature detection.
- Billing and telemetry side effects.

Add fixtures here when extending parity instead of shelling out to Node from Python tests.
