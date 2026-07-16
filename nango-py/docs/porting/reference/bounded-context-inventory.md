# Reference: Bounded context inventory

> All 17 bounded contexts in the Python port, their layers, and what they own.

## Directory structure

```
src/nango_py/
  auth/              # Authentication: resolve bearer token → AuthenticatedContext
  auth_flows/        # Auth flows: create connections via API key, OAuth, JWT, etc.
  connect_sessions/  # Connect sessions: create/get/delete session tokens
  connections/       # Connections: list, get, CRUD, credential refresh
  contracts/         # Shared Pydantic request/response models
  deploy/            # Deploy: nango.yaml parsing + deploy validation
  integrations/      # Integrations: list, get, CRUD, provider catalog
  jobs/              # Jobs: processor dispatches to runner, callback routes
  keystore/          # Keystore: private key storage + encryption
  misc/              # Misc: MCP, remote functions, v1 passthrough, config
  nango_yaml/        # nango.yaml parser (compatible with TS packages/nango-yaml)
  proxy/             # Proxy: forward requests to provider APIs with retries
  public_records/    # Public records: GET /records, prune, env vars, scripts config
  pubsub/            # Pubsub: event envelope + publisher
  records/           # Records/persist: upsert, delete, list, checkpoints
  scheduler/         # Scheduler/orchestrator: task lifecycle, dequeue, recurring
  server/            # Composition root: create_app() wires everything
  shared/            # Shared: errors, crypto, serialize helpers
  sync_control/      # Sync control: trigger, pause, start, status, action trigger
  webhooks/          # Webhooks: ingress, delivery, circuit breaker
```

## Context details

### auth
**Purpose:** Resolve a bearer token to an `AuthenticatedContext` (account, environment, secret, scopes).

| Layer | Files | Responsibility |
|-------|-------|----------------|
| domain | `context.py`, `errors.py` | `Account`, `Environment`, `ApiSecret`, `Scopes`, `AuthenticatedContext` dataclasses; `Forbidden`, `MissingAuthHeader` errors |
| application | `gateway.py` | `AuthGateway` Protocol: `resolve_by_secret_key`, `resolve_by_internal_secret_key`, `resolve_by_public_key`, `resolve_by_connect_session_token` |
| infrastructure | `sqlalchemy_auth_gateway.py` | `SqlAlchemyAuthGateway`: queries `api_secrets`, `customer_keys`, `_nango_environments`, `connect_sessions` |
| transport | `dependencies.py`, `connect_session_auth.py` | `api_auth()` and `connect_session_auth()` FastAPI dependencies |

### auth_flows
**Purpose:** Create connections via non-OAuth auth modes (API key, basic, JWT, TBA, etc.).

| Layer | Files | Responsibility |
|-------|-------|----------------|
| domain | `oauth2.py`, `errors.py` | OAuth2 URL builder, state encoding; `InvalidAuthMode`, `UnknownProviderTemplate` |
| application | `create_auth_connection.py` | `CreateAuthConnection` use case |
| transport | `routes.py` | 13 auth flow routes + OAuth connect/callback |

### connect_sessions
**Purpose:** Create, read, delete connect session tokens for the Connect UI.

| Layer | Files | Responsibility |
|-------|-------|----------------|
| domain | `session.py` | `ConnectSession` dataclass |
| application | `use_cases.py`, `gateway.py` | `CreateConnectSession`, `GetConnectSessionByToken`, `DeleteConnectSession` |
| infrastructure | `sqlalchemy_connect_session_repository.py` | Session token storage + keystore integration |
| transport | `routes.py` | POST/GET/DELETE `/connect/session*`, telemetry |

### connections
**Purpose:** Connection reads (list, get), CRUD (create, patch, delete, metadata), credential refresh.

| Layer | Files | Responsibility |
|-------|-------|----------------|
| domain | `connection.py`, `credentials.py`, `errors.py`, `refresh.py` | `Connection` dataclass, `UnknownProviderConfig`, `ConnectionNotFound` |
| application | `gateway.py`, `get_connection.py`, `list_connections.py`, `crud.py`, `credential_refresher.py` | Use cases + `ConnectionRepository` Protocol |
| infrastructure | `sqlalchemy_connection_repository.py` | SQL queries against `_nango_connections` with joins |
| transport | `routes.py`, `serialize.py` | 15 connection routes + serialization |

### deploy
**Purpose:** Parse `nango.yaml` and validate deploy payloads.

| Layer | Files | Responsibility |
|-------|-------|----------------|
| domain | `errors.py` | Deploy validation errors |
| application | `validator.py` | `DeployValidator`: extract sync/action metadata |
| transport | `routes.py` | POST `/sync/deploy`, `/confirmation`, `/internal` |

### integrations
**Purpose:** Integration reads (list, get), CRUD (create, patch, delete, quickstart), provider catalog.

| Layer | Files | Responsibility |
|-------|-------|----------------|
| domain | `integration.py`, `provider.py`, `errors.py` | `Integration`, `Provider`, `PublicIntegrationView`; `IntegrationNotFound`, `ProviderNotFound` |
| application | `gateway.py`, `get_integration.py`, `list_integrations.py`, `crud.py` | Use cases + `IntegrationRepository`/`ProviderCatalog` Protocols |
| infrastructure | `sqlalchemy_integration_repository.py`, `provider_catalog.py` | SQL + YAML provider catalog (785 providers) |
| transport | `routes.py`, `serialize.py` | 9 integration + provider routes |

### jobs
**Purpose:** Dispatch tasks to the Node runner and process results.

| Layer | Files | Responsibility |
|-------|-------|----------------|
| domain | `runner_boundary.py` | `RunnerStartParams`, `RunnerTaskResult`, `NodeRunnerClient` |
| application | `processor.py` | `JobsProcessorService`: dispatch + complete |
| transport | `routes.py` | PUT `/jobs/tasks/{task_id}`, POST heartbeat |

### keystore
**Purpose:** Encrypted private key storage for connect sessions.

| Layer | Files | Responsibility |
|-------|-------|----------------|
| domain | `private_key.py`, `errors.py` | `PrivateKey` dataclass |
| application | `gateway.py` | `PrivateKeyRepository` Protocol |
| infrastructure | `sqlalchemy_private_key_repository.py` | AES-GCM encrypted key storage |

### proxy
**Purpose:** Forward requests to provider APIs with auth, retries, and credential refresh.

| Layer | Files | Responsibility |
|-------|-------|----------------|
| domain | `config.py`, `headers.py`, `url.py`, `retry.py`, `interpolate.py`, `denylist.py`, `errors.py` | URL/header building, retry logic, base URL denylist |
| application | `proxy_request.py` | `ProxyRequest` use case with retry loop + 401 refresh |
| transport | `routes.py` | `ALL /proxy/{path}` |

### records
**Purpose:** Record persistence (upsert, update, delete, list) + checkpoints + persist routes.

| Layer | Files | Responsibility |
|-------|-------|----------------|
| domain | `record.py` | `Record`, `RecordInput`, `RecordCheckpoint`, `ListRecordsResult` |
| application | `gateway.py` | `RecordsRepository` Protocol |
| infrastructure | `postgres_records_repository.py` | Upsert with deterministic UUID5, MD5 hash, partitioned tables |
| transport | `routes.py` | 11 persist routes + health |

### scheduler
**Purpose:** Task lifecycle (create, dequeue, heartbeat, transition) + recurring schedules.

| Layer | Files | Responsibility |
|-------|-------|----------------|
| domain | `models.py` | `Task`, `Schedule`, `ImmediateTaskInput`, `RecurringScheduleInput` |
| application | `orchestrator_service.py` | `OrchestratorService`: create, dequeue, transition, search |
| infrastructure | `postgres_scheduler_repository.py` | Postgres `tasks`/`schedules` tables |
| transport | `routes.py` | 12 orchestrator routes |

### sync_control
**Purpose:** Sync control routes (trigger, pause, start, status) + action trigger/result.

| Layer | Files | Responsibility |
|-------|-------|----------------|
| transport | `routes.py` | 8 sync + action routes, scope checks |

### webhooks
**Purpose:** Webhook ingress + delivery with circuit breaker.

| Layer | Files | Responsibility |
|-------|-------|----------------|
| — | `delivery.py`, `circuit_breaker.py` | Webhook delivery logic, circuit breaker pattern |
| transport | `routes.py` | POST `/webhook/{env_uuid}/{pck}` |

### misc
**Purpose:** MCP, remote functions, v1 passthrough, deprecated config, app-auth.

| Layer | Files | Responsibility |
|-------|-------|----------------|
| transport | `routes.py` | MCP, remote function, v1, config, app-auth routes |

### shared
**Purpose:** Cross-cutting concerns used by all contexts.

| Files | Responsibility |
|-------|----------------|
| `errors.py` | `ApiError`, `NangoApiError`, `ValidationApiError` base classes |
| `crypto.py` | AES-GCM encrypt/decrypt, secret hashing |
| `serialize.py` | Shared serialization helpers |

### contracts
**Purpose:** Shared Pydantic request/response models.

| Files | Responsibility |
|-------|----------------|
| `base.py` | Base Pydantic model config |
| `connect.py` | `ConnectSessionCreateRequest` |