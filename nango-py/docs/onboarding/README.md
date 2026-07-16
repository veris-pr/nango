# Nango Platform — Developer Onboarding

> **Audience:** New developers joining the Nango platform team. This guide
> takes you from zero to productive contributor.

This documentation set follows the [Diátaxis](https://diataxis.fr) framework —
four quadrants, each serving a different stage of learning.

## What Nango is

Nango is an open-source platform for managing OAuth and API key connections to
external providers (Google, GitHub, HubSpot, Salesforce, etc.). It handles auth
flows, connection storage, credential refresh, proxying requests to provider
APIs, running sync/action scripts, and delivering webhooks.

The backend was originally written in TypeScript. It is being ported to Python
(`nango-py/`). Both backends share the same Postgres database, provider catalog,
and API contracts. The TypeScript code is the **source of truth** for contracts.

## Where to start

```
                    ┌─────────────────────┬─────────────────────┐
                    │    Tutorials        │   How-to guides     │
                    │  (learning-oriented) │  (task-oriented)    │
 NEW HERE           │                     │                     │
                    │  Start here. These   │  Come here when you │
                    │  walk you through    │  have a specific    │
                    │  setup and your      │  task like adding   │
                    │  first change        │  an endpoint        │
                    ├─────────────────────┼─────────────────────┤
                    │    Reference        │   Explanation       │
                    │ (information-oriented)│ (understanding)   │
                    │                     │                     │
                    │  Come here for the   │  Come here to       │
                    │  architecture map,   │  understand why     │
                    │  module catalog,    │  things are designed │
                    │  and data contracts  │  the way they are   │
                    └─────────────────────┴─────────────────────┘
```

### Tutorials — *Start here*
- [Set up your dev environment](./tutorials/01-set-up-your-dev-environment.md) — Get the repo running locally
- [Run the server locally](./tutorials/02-run-the-server-locally.md) — Start both backends and hit an API
- [Make your first change](./tutorials/03-make-your-first-change.md) — Add a field to an API response
- [Run your first test](./tutorials/04-run-your-first-test.md) — Execute the test suite

### How-to guides — *When you have a task*
- [Add a new API endpoint](./how-to/add-a-new-endpoint.md) — End-to-end: domain → transport → test
- [Add a new provider](./how-to/add-a-new-provider.md) — Extend the provider catalog
- [Debug a failing test](./how-to/debug-a-failing-test.md) — Diagnose test failures
- [Understand the data flow](./how-to/understand-the-data-flow.md) — Trace a request through the system

### Reference — *When you need the facts*
- [Architecture overview](./reference/architecture-overview.md) — System diagram and service boundaries
- [Bounded context catalog](./reference/bounded-context-catalog.md) — All modules and what they own
- [Data flow reference](./reference/data-flow-reference.md) — Request lifecycle through all layers
- [Data contracts](./reference/data-contracts.md) — API shapes, error envelopes, DB schemas
- [Module reference](./reference/module-reference.md) — Key classes, functions, and their responsibilities

### Explanation — *When you want to understand why*
- [Architecture decisions](./explanation/architecture-decisions.md) — Why DDD, why Python, why raw SQL
- [How auth works](./explanation/how-auth-works.md) — The auth pipeline from header to AuthenticatedContext
- [The cutover plan](./explanation/the-cutover-plan.md) — Why one coordinated release
- [DDD layering rationale](./explanation/ddd-layering-rationale.md) — Why four layers per context