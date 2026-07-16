# Nango Python Core

Active contract-first Python implementation of selected Nango backend service boundaries.

Current status: bootstrap only. No public or internal Nango route is implemented or eligible
for production traffic. Python remains offline until the complete backend replacement passes
all readiness gates. The previous prototype is archived under `../python-core-spike/` and must
not be copied wholesale.

Execution plan: [`../dev/docs/PythonCoreImplementationPlan.md`](../dev/docs/PythonCoreImplementationPlan.md)

## Setup

```bash
cd nango-py
uv sync --extra dev
```

## Verification

```bash
uv lock --check
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

Cutover strategy is fixed: one coordinated full replacement, no production shadow/canary or
traffic splitting, with verified TypeScript artifacts retained temporarily for emergency
rollback.

## Documentation

- [Python Port Guide](./docs/porting/README.md) — for engineers porting, extending, or
  verifying the Python core (tutorials, how-to, reference, explanation)
- [Developer Onboarding](./docs/onboarding/README.md) — for new developers joining the
  platform (setup, architecture, data flow, contracts, module reference)
