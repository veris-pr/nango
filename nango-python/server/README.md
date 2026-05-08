# Nango Python Core Skeleton

This directory is an incremental Python core skeleton. It runs beside the existing
TypeScript services and does not replace any current Nango service.

## Setup

```bash
cd nango-python/server
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Add Redis support only when a task needs it:

```bash
python -m pip install -e ".[redis]"
```

## Local commands

```bash
python -m ruff check .
python -m mypy
python -m pytest
python -m uvicorn nango.server.app:create_app --factory --reload
```

The health route is `GET /health`; it reports service status and cutover metadata.

## Contract DTO checks

Representative Python DTOs live in `nango/contracts`. Their neutral JSON
fixtures live in `contract-fixtures` and intentionally cover only a small
foundation: health, Connect sessions, pubsub events, and webhook signature
metadata.

Run the lightweight drift check with:

```bash
python scripts/check_contract_fixtures.py
```

This validates that checked-in fixture field names and JSON datetime
serialization still round-trip through the Pydantic DTOs. Extend the fixtures
before adding broader TypeScript contract coverage.
