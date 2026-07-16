# Reference: Route parity matrix

> Authoritative list of all TypeScript public API routes and their Python
> counterparts. Last updated: Phase 9 + route parity complete (75 Python routes).

## Summary

| Metric | Count |
|--------|-------|
| TS public API routes | 53 |
| TS persist routes | 7 |
| TS orchestrator routes | 11 |
| **Total TS routes** | **71** |
| **Python routes** | **75** |
| **Missing from Python** | **0** |

The 4 extra Python routes are internal: `/jobs/tasks/*`, `/daemon/*`.

## Public API routes

### Auth flows

| TS route | Python route | Status |
|----------|-------------|--------|
| `POST /api-auth/api-key/:pck` | `POST /api-auth/api-key/{provider_config_key}` | ✅ |
| `POST /api-auth/basic/:pck` | `POST /api-auth/basic/{provider_config_key}` | ✅ |
| `POST /app-store-auth/:pck` | `POST /app-store-auth/{provider_config_key}` | ✅ |
| `POST /auth/bill/:pck` | `POST /auth/bill/{provider_config_key}` | ✅ |
| `POST /auth/jwt/:pck` | `POST /auth/jwt/{provider_config_key}` | ✅ |
| `POST /auth/oauth-outbound/:pck` | `POST /auth/oauth-outbound/{provider_config_key}` | ✅ |
| `POST /auth/signature/:pck` | `POST /auth/signature/{provider_config_key}` | ✅ |
| `POST /auth/tba/:pck` | `POST /auth/tba/{provider_config_key}` | ✅ |
| `POST /auth/two-step/:pck` | `POST /auth/two-step/{provider_config_key}` | ✅ |
| `POST /auth/unauthenticated/:pck` | `POST /auth/unauthenticated/{provider_config_key}` | ✅ |
| `GET /oauth/connect/:pck` | `GET /oauth/connect/{provider_config_key}` | ✅ |
| `GET /oauth/callback` | `GET /oauth/callback/{provider_config_key}` | ✅ |
| `POST /oauth2/auth/:pck` | `POST /oauth2/auth/{provider_config_key}` | ✅ |

### Integrations

| TS route | Python route | Status |
|----------|-------------|--------|
| `GET /integrations` | `GET /integrations` | ✅ |
| `POST /integrations` | `POST /integrations` | ✅ |
| `POST /integrations/quickstart` | `POST /integrations/quickstart` | ✅ |
| `GET /integrations/:uniqueKey` | `GET /integrations/{unique_key}` | ✅ |
| `PATCH /integrations/:uniqueKey` | `PATCH /integrations/{unique_key}` | ✅ |
| `DELETE /integrations/:uniqueKey` | `DELETE /integrations/{unique_key}` | ✅ |
| `GET /providers` | `GET /providers` | ✅ |
| `GET /providers/:provider` | `GET /providers/{provider}` | ✅ |
| `GET /config/:pck` (deprecated) | `GET /config/{provider_config_key}` | ✅ |

### Connections

| TS route | Python route | Status |
|----------|-------------|--------|
| `GET /connections` | `GET /connections` | ✅ |
| `POST /connections` | `POST /connections` | ✅ |
| `GET /connections/:connectionId` | `GET /connections/{connection_id}` | ✅ |
| `PATCH /connections/:connectionId` | `PATCH /connections/{connection_id}` | ✅ |
| `DELETE /connections/:connectionId` | `DELETE /connections/{connection_id}` | ✅ |
| `POST /connections/metadata` | `POST /connections/metadata` | ✅ |
| `PATCH /connections/metadata` | `PATCH /connections/metadata` | ✅ |
| `GET /connection` (deprecated) | `GET /connection` | ✅ |
| `POST /connection` (deprecated) | `POST /connection` | ✅ |
| `GET /connection/:connectionId` (deprecated) | `GET /connection/{connection_id}` | ✅ |
| `DELETE /connection/:connectionId` (deprecated) | `DELETE /connection/{connection_id}` | ✅ |
| `POST /connection/metadata` (deprecated) | `POST /connection/metadata` | ✅ |
| `PATCH /connection/metadata` (deprecated) | `PATCH /connection/metadata` | ✅ |
| `POST /connection/:connectionId/metadata` (deprecated) | `POST /connection/{connection_id}/metadata` | ✅ |
| `PATCH /connection/:connectionId/metadata` (deprecated) | `PATCH /connection/{connection_id}/metadata` | ✅ |

### Connect sessions

| TS route | Python route | Status |
|----------|-------------|--------|
| `POST /connect/sessions` | `POST /connect/sessions` | ✅ |
| `POST /connect/sessions/reconnect` | `POST /connect/sessions/reconnect` | ✅ |
| `GET /connect/session` | `GET /connect/session` | ✅ |
| `DELETE /connect/session` | `DELETE /connect/session` | ✅ |
| `POST /connect/telemetry` | `POST /connect/telemetry` | ✅ |

### Syncs & actions

| TS route | Python route | Status |
|----------|-------------|--------|
| `POST /sync/trigger` | `POST /sync/trigger` | ✅ |
| `POST /sync/pause` | `POST /sync/pause` | ✅ |
| `POST /sync/start` | `POST /sync/start` | ✅ |
| `GET /sync/status` | `GET /sync/status` | ✅ |
| `PUT /sync/update-connection-frequency` | `PUT /sync/update-connection-frequency` | ✅ |
| `POST /sync/:name/variant/:variant` | `POST /sync/{name}/variant/{variant}` | ✅ |
| `DELETE /sync/:name/variant/:variant` | `DELETE /sync/{name}/variant/{variant}` | ✅ |
| `POST /action/trigger` | `POST /action/trigger` | ✅ |
| `GET /action/:id` | `GET /action/{action_id}` | ✅ |

### Deploy

| TS route | Python route | Status |
|----------|-------------|--------|
| `POST /sync/deploy` | `POST /sync/deploy` | ✅ |
| `POST /sync/deploy/confirmation` | `POST /sync/deploy/confirmation` | ✅ |
| `POST /sync/deploy/internal` | `POST /sync/deploy/internal` | ✅ |

### Records & proxy

| TS route | Python route | Status |
|----------|-------------|--------|
| `GET /records` | `GET /records` | ✅ |
| `PATCH /records/prune` | `PATCH /records/prune` | ✅ |
| `ALL /proxy/*splat` | `ALL /proxy/{path}` | ✅ |

### Other

| TS route | Python route | Status |
|----------|-------------|--------|
| `GET /environment-variables` | `GET /environment-variables` | ✅ |
| `GET /scripts/config` | `GET /scripts/config` | ✅ |
| `POST /mcp` | `POST /mcp` | ✅ |
| `GET /mcp` | `GET /mcp` | ✅ |
| `POST /remote-function/compile` | `POST /remote-function/compile` | ✅ |
| `POST /remote-function/dryrun` | `POST /remote-function/dryrun` | ✅ |
| `POST /remote-function/deploy` | `POST /remote-function/deploy` | ✅ |
| `ALL /v1/*splat` | `ALL /v1/{path}` | ✅ |
| `POST /webhook/:envUuid/:pck` | `POST /webhook/{environment_uuid}/{provider_config_key}` | ✅ |
| `GET /app-auth/connect` | `GET /app-auth/connect` | ✅ |

## Persist service routes

| TS route | Python route | Status |
|----------|-------------|--------|
| `GET /health` | `GET /health` | ✅ |
| `POST /environment/:envId/log` | `POST /environment/{environment_id}/log` | ✅ |
| `POST .../records` | `POST .../records` | ✅ |
| `DELETE .../records` | `DELETE .../records` | ✅ |
| `DELETE .../outdated-records` | `DELETE .../outdated-records` | ✅ |
| `PUT .../records` | `PUT .../records` | ✅ |
| `GET .../cursor` | `GET .../cursor` | ✅ |
| `GET .../records` | `GET .../records` | ✅ |
| `GET .../checkpoint` | `GET .../checkpoint` | ✅ |
| `PUT .../checkpoint` | `PUT .../checkpoint` | ✅ |
| `DELETE .../checkpoint` | `DELETE .../checkpoint` | ✅ |

## Orchestrator service routes

| TS route | Python route | Status |
|----------|-------------|--------|
| `GET /v1/health` | `GET /orchestrator/v1/health` | ✅ |
| `POST /v1/immediate` | `POST /orchestrator/v1/immediate` | ✅ |
| `POST /v1/recurring` | `POST /orchestrator/v1/recurring` | ✅ |
| `PUT /v1/recurring` | `PUT /orchestrator/v1/recurring` | ✅ |
| `POST /v1/dequeue` | `POST /orchestrator/v1/dequeue` | ✅ |
| `POST /v1/tasks/:taskId/heartbeat` | `POST /orchestrator/v1/tasks/{task_id}/heartbeat` | ✅ |
| `PUT /v1/tasks/:taskId` | `PUT /orchestrator/v1/tasks/{task_id}` | ✅ |
| `GET /v1/tasks/:taskId/output` | `GET /orchestrator/v1/tasks/{task_id}/output` | ✅ |
| `POST /v1/tasks/search` | `POST /orchestrator/v1/tasks/search` | ✅ |
| `POST /v1/schedules/search` | `POST /orchestrator/v1/schedules/search` | ✅ |
| `POST /v1/schedules/run` | `POST /orchestrator/v1/schedules/run` | ✅ |
| `GET /v1/retries/:retryKey/output` | `GET /orchestrator/v1/retries/{retry_key}/output` | ✅ |