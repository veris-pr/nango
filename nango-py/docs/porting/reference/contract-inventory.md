# Reference: Contract inventory

> Frozen first-pass TypeScript contract inventory for the Python core migration.
> Condensed from `dev/docs/PythonCoreContractInventory.md`.

## Scope decisions

| Area | Migration stance |
|------|-----------------|
| Public APIs | Preserve paths, headers, query, response shapes, webhook signatures |
| CLI deploy/config | Preserve nango.yaml parsing + deploy payloads + server validation |
| Internal services | Preserve RPC contracts between server/jobs/runner/persist/orchestrator/scheduler |
| Usage/metering | In scope. Preserve usage pubsub events + storage contracts |
| Billing | Out of scope. Stripe, Orb, billing providers not ported |
| Telemetry | Out of scope. No new telemetry, tracing, metrics exporters |
| Logs | Prefer Postgres-backed operational logs. ES optional compatibility |

## Contract sources

Most durable API shapes live in `@nangohq/types`:
- `packages/types/lib/api.ts` — `Endpoint<>` convention
- `packages/types/lib/api.endpoints.ts` — endpoint union

Implementation packages consume those types:
- `packages/server/lib/routes.public.ts` — public server routes
- `packages/node-client/lib/index.ts` — public SDK
- `packages/frontend/lib/index.ts` — browser SDK
- `packages/connect-ui/src/lib/api.ts` — Connect UI

## 1. Public API contracts

### Shared conventions

- Bearer authorization: `Authorization: Bearer <secretKey>`
- Execution context headers: `Nango-Is-Sync`, `Nango-Is-Script`, `Nango-Is-Dry-Run`
- Case-insensitive HTTP header handling
- Endpoint shapes typed with `Endpoint<>`

### API families

| Family | Endpoints | Type source |
|--------|----------|-------------|
| Providers | `GET /providers`, `GET /providers/:provider` | `types/lib/providers/api.ts` |
| Integrations | `GET/POST /integrations`, `GET/PATCH/DELETE /integrations/:uniqueKey`, `POST /integrations/quickstart` | `types/lib/integration/api.ts` |
| Connections | `GET /connections`, `GET/PATCH/DELETE /connections/:id`, `POST/PATCH /connections/metadata` | `types/lib/connection/api/get.ts` |
| Records | `GET /records`, `PATCH /records/prune` | `types/lib/record/api.ts` |
| Syncs | `POST /sync/trigger`, `/pause`, `/start`, `GET /sync/status`, `PUT /sync/update-connection-frequency`, `POST/DELETE /sync/:name/variant/:variant` | `types/lib/sync/api.ts` |
| Actions | `POST /action/trigger`, `GET /action/:id` | `types/lib/action/api.ts` |
| Proxy | `ALL /proxy/:endpoint` with proxy headers | `node-client/lib/index.ts` |
| Connect sessions | `POST /connect/sessions`, `POST /connect/sessions/reconnect` | `types/lib/connect/api.ts` |

## 2. Internal service contracts

### Service responsibilities

| Service | Responsibility |
|---------|---------------|
| `server` | Public API facade. Schedules actions/syncs/webhooks via orchestrator |
| `orchestrator` | HTTP API over scheduler state. Owns task + schedule RPCs |
| `scheduler` | Postgres-backed task + schedule state machine. Dequeue, heartbeat, retries, concurrency |
| `jobs` | Long-polls orchestrator, prepares execution, starts runner, receives results, updates orchestrator |
| `runner` | Executes JS/TS customer functions. Receives code + NangoProps, heartbeats, sends output |
| `persist` | HTTP service for records, checkpoints, persistence operations |
| `metering` | Consumes usage/team pubsub events, writes usage storage |

### Orchestrator endpoints

| Endpoint | Contract |
|----------|---------|
| `POST /v1/immediate` | Create immediate task. Returns `{ taskId, retryKey }` |
| `POST /v1/recurring` | Create recurring schedule. Returns `{ scheduleId }` |
| `POST /v1/dequeue` | Long-poll task dequeue with `{ groupKeyPattern, limit, longPolling }` |
| `POST /v1/tasks/:taskId/heartbeat` | Update task heartbeat |
| `PUT /v1/tasks/:taskId` | Complete task with `{ output, state, nextExecutionInMs? }` |

### Task payload types

- `sync`: `syncId`, `syncName`, `syncVariant`, `debug`, `connection`
- `action`: `actionName`, `activityLogId`, `input`, `async`, `connection`
- `webhook`: `webhookName`, `parentSyncName`, `activityLogId`, `input`, `connection`
- `on-event`: `onEventName`, `version`, `fileLocation`, `sdkVersion`, `activityLogId`, `connection`

### Jobs/runner contract

- Runner tRPC: `health`, `start`, `abort`, `notifyWhenIdle`
- Runner `start` params: `{ taskId, nangoProps, code, codeParams? }`
- Jobs callback: `PUT /tasks/:taskId` with `{ nangoProps?, error?, output?, telemetryBag, functionRuntime, checkpoints? }`
- Jobs heartbeat: `POST /tasks/:taskId/heartbeat`

### Persist contract

- Auth path: `/environment/:environmentId/*`
- Records path: `.../connection/:nangoConnectionId/sync/:syncId/job/:syncJobId/records`
- Record mutations: `{ model, records, providerConfigKey, connectionId, activityLogId, merging }` → `{ nextMerging }`

## 3. Pubsub event contracts

```ts
{
  idempotencyKey: string;
  subject: string;
  type: string;
  payload: Serializable;
  source?: string;
  createdAt: Date;
}
```

Event types:

| Subject | Type | Payload |
|---------|------|---------|
| `user` | `user.created` | `{ userId, teamId }` |
| `team` | `team.updated` | `{ id }` |
| `usage` | `usage.records` | Common usage + `syncId`, `model` |
| `usage` | `usage.actions` | Common usage + `actionName` |
| `usage` | `usage.connections` | Common usage |
| `usage` | `usage.function_executions` | Common usage + `type`, `success`, `functionName` |
| `usage` | `usage.proxy` | Common usage + `success` |

## 4. Webhook contracts

### Outgoing Nango webhooks

- `X-Nango-Hmac-Sha256`: HMAC-SHA256 over stable JSON body using environment webhook secret
- `X-Nango-Signature`: deprecated SHA256 of `secret + payload`
- `content-type: application/json`

Payload types:

| Type | Contract |
|------|---------|
| `sync` | `from: 'nango'`, `type: 'sync'`, `connectionId`, `providerConfigKey`, `syncName`, `model`, optional `checkpoints` |
| `auth` | `from: 'nango'`, `type: 'auth'`, `connectionId`, `providerConfigKey`, `authMode`, `provider`, `operation` |
| `async_action` | `from: 'nango'`, `type: 'async_action'`, `connectionId`, `providerConfigKey`, `payload: { id, statusUrl }` |
| `forward` | `from: <provider>`, `type: 'forward'`, `providerConfigKey`, `connectionId`, `payload` |

### Incoming provider webhooks

- Route: `POST /webhook/:environmentUuid/:providerConfigKey`
- Handlers receive `headers`, `body`, `rawBody`, `query`
- Results may include `connectionIds` and `toForward`
- HMAC validation via `X-Nango-Hmac-Sha256`