# Reference: Bounded context catalog

> All 17 bounded contexts in the Python port, what they own, and their key
> classes.

## auth

**Owns:** Authentication — resolve bearer token to `AuthenticatedContext`.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| domain | `AuthenticatedContext` | Account + Environment + Scopes + Secret |
| domain | `Scopes` | Wildcard scope matching (`has`, `has_any`) |
| application | `AuthGateway` (Protocol) | `resolve_by_secret_key`, `resolve_by_internal_secret_key`, `resolve_by_public_key`, `resolve_by_connect_session_token` |
| infrastructure | `SqlAlchemyAuthGateway` | Queries `api_secrets`, `customer_keys`, `connect_sessions` |
| transport | `api_auth()` | FastAPI dependency for bearer token auth |
| transport | `connect_session_auth()` | FastAPI dependency for connect session auth |

## auth_flows

**Owns:** Creating connections via non-OAuth auth modes.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| domain | `build_oauth2_connect_url()` | Build OAuth2 authorization URL |
| application | `CreateAuthConnection` | Create connection with credentials |
| transport | 13 auth flow routes | API key, basic, JWT, TBA, two-step, bill, signature, app-store, OAuth2 CC, OAuth outbound, unauthenticated, OAuth connect/callback |

## connect_sessions

**Owns:** Connect session tokens for the Connect UI.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| domain | `ConnectSession` | Session data shape |
| application | `CreateConnectSession` | Create session token |
| application | `GetConnectSessionByToken` | Resolve token to session data |
| application | `DeleteConnectSession` | Delete session |
| infrastructure | `SqlAlchemyConnectSessionRepository` | Session storage + keystore |
| transport | 5 routes | POST/GET/DELETE session, reconnect, telemetry |

## connections

**Owns:** Connection reads, CRUD, metadata, credential refresh.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| domain | `Connection` | Connection dataclass |
| domain | `UnknownProviderConfig`, `ConnectionNotFound` | Typed errors |
| application | `ListConnections` | List with filters + pagination |
| application | `GetConnection` | Get single with credential decryption |
| application | `ConnectionCrudService` | Create, patch, delete, metadata |
| application | `CredentialRefresher` | OAuth2 token refresh |
| infrastructure | `SqlAlchemyConnectionRepository` | SQL against `_nango_connections` |
| transport | 15 routes | List, get, create, patch, delete, metadata (new + deprecated) |

## deploy

**Owns:** nango.yaml parsing and deploy validation.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| application | `DeployValidator` | Parse nango.yaml, extract sync/action metadata |
| transport | 3 routes | POST deploy, confirmation, internal |

## integrations

**Owns:** Integration reads, CRUD, provider catalog.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| domain | `Integration`, `Provider` | Domain dataclasses |
| domain | `PublicIntegrationView` | Response view shape |
| application | `GetIntegration` | Read integration with credential visibility policy |
| application | `ListIntegrations` | List integrations for environment |
| application | `IntegrationCrudService` | Create, patch, delete, quickstart |
| application | `IntegrationRepository` (Protocol) | DB access port |
| application | `ProviderCatalog` (Protocol) | Provider lookup port |
| infrastructure | `SqlAlchemyIntegrationRepository` | SQL against `_nango_configs` |
| infrastructure | `YamlProviderCatalog` | Loads 785-provider `providers.yaml` |
| transport | 9 routes | List, get, create, patch, delete, quickstart, providers list, provider get |

## jobs

**Owns:** Dispatching tasks to the Node runner and processing results.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| domain | `RunnerStartParams`, `RunnerTaskResult` | Runner boundary types |
| domain | `NodeRunnerClient` | Runner client |
| application | `JobsProcessorService` | Dispatch + complete + heartbeat |
| transport | 2 routes | PUT task result, POST heartbeat |

## keystore

**Owns:** Encrypted private key storage.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| domain | `PrivateKey` | Key dataclass |
| application | `PrivateKeyRepository` (Protocol) | Storage port |
| infrastructure | `SqlAlchemyPrivateKeyRepository` | AES-GCM encrypted storage |

## proxy

**Owns:** Forwarding requests to provider APIs with retries.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| domain | `build_proxy_url()` | URL construction with template interpolation |
| domain | `build_proxy_headers()` | Header construction per auth mode |
| domain | `get_proxy_retry_from_err()` | Retry decision from response |
| domain | `is_base_url_override_denied()` | Base URL denylist check |
| application | `ProxyRequest` | Execute with retries + 401 credential refresh |
| transport | 1 route | `ALL /proxy/{path}` |

## public_records

**Owns:** Public records read + environment variables + scripts config.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| transport | 4 routes | GET records, PATCH prune, GET env vars, GET scripts config |

## records

**Owns:** Record persistence + checkpoints + persist routes.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| domain | `Record`, `RecordInput`, `RecordCheckpoint` | Record data shapes |
| application | `RecordsRepository` (Protocol) | Storage port |
| infrastructure | `PostgresRecordsRepository` | Upsert with UUID5 + MD5 hash, partitioned tables |
| transport | 11 routes | Records CRUD, checkpoints, cursor, health, daemon |

## scheduler

**Owns:** Task lifecycle + recurring schedules.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| domain | `Task`, `Schedule` | State dataclasses |
| domain | `ImmediateTaskInput`, `RecurringScheduleInput` | Creation inputs |
| application | `OrchestratorService` | Create, dequeue, transition, search |
| infrastructure | `PostgresSchedulerRepository` | SQL against `tasks`/`schedules` |
| transport | 12 routes | Immediate, recurring, dequeue, heartbeat, transition, search, output |

## sync_control

**Owns:** Sync control + action trigger/result.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| transport | 8 routes | Trigger, pause, start, status, frequency, variants, action trigger, action result |

## webhooks

**Owns:** Webhook ingress + delivery.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| — | `WebhookDelivery` | Outgoing webhook delivery logic |
| — | `CircuitBreaker` | Circuit breaker pattern |
| transport | 1 route | POST `/webhook/{env_uuid}/{pck}` |

## misc

**Owns:** MCP, remote functions, v1 passthrough, deprecated config, app-auth.

| Layer | Key class | Responsibility |
|-------|-----------|----------------|
| transport | 10 routes | MCP, remote function compile/dryrun/deploy, v1 passthrough, config, app-auth |

## shared

**Owns:** Cross-cutting concerns.

| File | Key class | Responsibility |
|------|-----------|----------------|
| `errors.py` | `ApiError`, `NangoApiError`, `ValidationApiError` | Error envelope base classes |
| `crypto.py` | `encrypt_aes_gcm()`, `decrypt_aes_gcm()`, `hash_secret()` | AES-GCM crypto + SHA-256 hashing |
| `serialize.py` | Serialization helpers | Dict conversion, ISO timestamps |

## contracts

**Owns:** Shared Pydantic request/response models.

| File | Key class | Responsibility |
|------|-----------|----------------|
| `connect.py` | `ConnectSessionCreateRequest` | Connect session create body model |