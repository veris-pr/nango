# Reference: Module reference

> Key classes, functions, and their responsibilities. Quick lookup for
> daily development.

## auth

### `AuthenticatedContext` (`auth/domain/context.py`)
```python
@dataclass(frozen=True)
class AuthenticatedContext:
    account: Account
    environment: Environment
    secret: ApiSecret
    auth_source: AuthSource
    scopes: Scopes
    api_key_id: int | None = None
```
The context passed to every use case. Contains everything the use case needs
to know about who is calling.

### `Scopes` (`auth/domain/context.py`)
```python
class Scopes:
    granted: tuple[str, ...]
    def has(self, required: str) -> bool      # exact or wildcard match
    def has_any(self, required: tuple[str, ...]) -> bool
```
Implements TypeScript `hasScope` wildcard semantics.

### `AuthGateway` (`auth/application/gateway.py`)
```python
class AuthGateway(Protocol):
    async def resolve_by_secret_key(self, secret_key: str) -> AuthenticatedContext | None
    async def resolve_by_internal_secret_key(self, ...) -> AuthenticatedContext | None
    async def resolve_by_public_key(self, public_key: str) -> AuthenticatedContext | None
    async def resolve_by_connect_session_token(self, token: str) -> AuthenticatedContext | None
```

### `api_auth()` (`auth/transport/dependencies.py`)
FastAPI dependency. Extracts bearer token, validates UUID v4, resolves via
`AuthGateway`. Returns `AuthenticatedContext`.

### `connect_session_auth()` (`auth/transport/dependencies.py`)
FastAPI dependency for connect session tokens (prefix `nango_connect_session_`).

## shared

### `ApiError` (`shared/errors.py`)
```python
class ApiError(Exception):
    status: int = 500
    code: str = "unknown_error"
    message: str = ""
    def to_envelope(self) -> dict  # {"error": {"code": ..., "message": ...}}
```
Base for all errors that map to HTTP responses.

### `NangoApiError` (`shared/errors.py`)
```python
class NangoApiError(ApiError):
    payload: dict = {}
    def to_envelope(self) -> dict  # {"error": {"message": ..., "code": ..., "payload": {}}}
```
For auth errors (missing/malformed/invalid token).

### `ValidationApiError` (`shared/errors.py`)
```python
class ValidationApiError(ApiError):
    status = 400
    def __init__(self, code: str, errors: list[dict])
    def to_envelope(self) -> dict  # {"error": {"code": ..., "errors": [...]}}
```
For Zod-style validation failures with field paths.

### `encrypt_aes_gcm()` / `decrypt_aes_gcm()` (`shared/crypto.py`)
AES-256-GCM encryption for credentials. Returns `(ciphertext, iv, tag)` tuple.

### `hash_secret()` (`shared/crypto.py`)
SHA-256 hash for API secret storage.

## integrations

### `GetIntegration` (`integrations/application/get_integration.py`)
```python
class GetIntegration:
    async def execute(self, request: GetIntegrationRequest) -> PublicIntegrationView
```
Owns: scope check, integration lookup, provider resolution, credential
visibility policy, response view assembly.

### `IntegrationRepository` (`integrations/application/gateway.py`)
```python
class IntegrationRepository(Protocol):
    async def get_by_unique_key(self, *, environment_id: int, unique_key: str) -> Integration | None
    async def list_for_environment(self, *, environment_id: int) -> list[Integration]
```

### `ProviderCatalog` (`integrations/application/gateway.py`)
```python
class ProviderCatalog(Protocol):
    def get(self, name: str) -> Provider | None
    def entry(self, name: str) -> dict[str, object] | None
    def entries(self) -> dict[str, dict[str, object]]
```

### `YamlProviderCatalog` (`integrations/infrastructure/provider_catalog.py`)
Loads `packages/providers/providers.yaml` (785 providers), resolves aliases.
`from_path(path)` classmethod for construction.

### `PublicIntegrationView` (`integrations/domain/integration.py`)
```python
@dataclass(frozen=True)
class PublicIntegrationView:
    unique_key: str
    provider: str
    display_name: str
    logo: str
    forward_webhooks: bool
    created_at: datetime
    updated_at: datetime
    webhook_url: str | None | _NotSet = NOT_SET
    credentials: CredentialsView | None | _NotSet = NOT_SET
```
`NOT_SET` = omit from JSON. `None` = include as `null`.

## connections

### `GetConnection` (`connections/application/get_connection.py`)
```python
class GetConnection:
    async def execute(self, request: GetConnectionRequest) -> Connection
```
Decrypts credentials, strips refresh_token, applies read_credentials scope.

### `ListConnections` (`connections/application/list_connections.py`)
List with filters (connectionId, integrationId, search, endUserId, tags),
pagination, deleted exclusion. Never decrypts credentials.

### `ConnectionCrudService` (`connections/application/crud.py`)
```python
class ConnectionCrudService:
    async def create(self, request: CreateConnectionRequest) -> dict
    async def patch(self, request: PatchConnectionRequest) -> None
    async def delete(self, request: DeleteConnectionRequest) -> bool
    async def set_metadata(self, request: SetMetadataRequest) -> int
    async def update_metadata(self, request: SetMetadataRequest) -> int
```

### `CredentialRefresher` (`connections/application/credential_refresher.py`)
```python
class CredentialRefresher:
    async def refresh_if_needed(self, connection, integration, http_client) -> Connection
```
Checks if OAuth2 credentials need refresh, refreshes if expired, returns
updated connection.

## proxy

### `ProxyRequest` (`proxy/application/proxy_request.py`)
```python
class ProxyRequest:
    async def execute(self, request: ProxyRequestInput, http_client) -> ProxyResponse
```
Resolves connection, builds URL + headers, executes with retries. On 401,
refreshes credentials and retries. On 429/5xx, backoff retries.

### `build_proxy_url()` (`proxy/domain/url.py`)
Builds upstream URL from provider `proxy.base_url` + endpoint, with `${}`
template interpolation from connection_config.

### `build_proxy_headers()` (`proxy/domain/headers.py`)
Builds upstream headers per auth mode: Bearer (OAUTH2), Basic (BASIC), API key
(API_KEY), custom (SIGNATURE, TBA, etc.).

### `get_proxy_retry_from_err()` (`proxy/domain/retry.py`)
```python
def get_proxy_retry_from_err(*, status_code, headers, proxy_config, retry_on) -> RetryDecision
```
Returns `{retry: bool, reason: str}`. Retries on 401, 429, 5xx, and custom
`retry_on` statuses.

## scheduler

### `OrchestratorService` (`scheduler/application/orchestrator_service.py`)
```python
class OrchestratorService:
    async def create_immediate(self, input: ImmediateTaskInput) -> ImmediateTaskResponse
    async def create_recurring(self, input: RecurringScheduleInput) -> RecurringScheduleResponse
    async def dequeue(self, request: DequeueRequest) -> list[Task]
    async def heartbeat(self, task_id: str) -> HeartbeatResponse
    async def transition(self, task_id, state, output) -> Task
    async def get_task_output(self, task_id: str) -> JsonObject | None
    async def search_tasks(self, *, limit, offset) -> list[Task]
    async def search_schedules(self, *, limit, offset) -> list[Schedule]
    async def run_schedule(self, schedule_id: str) -> Task
    async def update_recurring(self, *, schedule_id, name, interval_ms) -> Schedule
    async def get_retry_output(self, retry_key: str) -> JsonObject | None
```

### `ImmediateTaskInput` (`scheduler/domain/models.py`)
```python
@dataclass(frozen=True)
class ImmediateTaskInput:
    name: str
    payload: JsonObject
    group_key: str
    group_max_concurrency: int
    retry_max: int
    retry_count: int
    retry_key: str | None
    owner_key: str | None
    starts_after: datetime
    created_to_started_timeout_secs: int
    started_to_completed_timeout_secs: int
    heartbeat_timeout_secs: int
```

## records

### `RecordsRepository` (`records/application/gateway.py`)
```python
class RecordsRepository(Protocol):
    async def upsert_records(self, *, environment_id, records) -> list[Record]
    async def update_records(self, *, environment_id, records) -> list[Record]
    async def delete_records(self, *, environment_id, connection_id, model, external_ids) -> int
    async def list_records(self, *, connection_id, model, limit, cursor, include_deleted) -> ListRecordsResult
    async def count_records(self, *, connection_id, model) -> int
    async def save_checkpoint(self, *, environment_id, connection_id, model, name, cursor) -> RecordCheckpoint
    async def get_checkpoint(self, *, environment_id, connection_id, model, name) -> RecordCheckpoint | None
    async def delete_checkpoint(self, *, environment_id, connection_id, model, name) -> None
    async def delete_outdated(self, *, environment_id, connection_id, model, sync_id, sync_job_id) -> int
```

### `PostgresRecordsRepository` (`records/infrastructure/postgres_records_repository.py`)
Implements all `RecordsRepository` methods against partitioned `records` +
`record_data` tables. Uses UUID5 for record IDs and MD5 for data hashes.

## server

### `create_app()` (`server/app.py`)
```python
def create_app(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    encryption_key: str,
    providers_path: str | Path | None = None,
    base_public_url: str | None = None,
    webhook_receive_url: str | None = None,
    httpx_transport: Any = None,
) -> FastAPI
```
The composition root. Creates all infrastructure adapters, use cases, and
routers. Registers the `ApiError` exception handler. Returns a ready-to-run
FastAPI app.