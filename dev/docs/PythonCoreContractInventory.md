# Python core contract inventory

**Status:** Contract reference for the active `nango-py/` implementation. See [Python core implementation plan](./PythonCoreImplementationPlan.md) for execution status and gates. The previous broad prototype is archived under `python-core-spike/`.

This document freezes the first-pass TypeScript contract inventory for the Python core migration. It is an implementation reference, not an implementation plan. Do not start a boundary from this document alone; generate authoritative TypeScript fixtures and satisfy the plan's compatibility gates first.

## Scope decisions

| Area              | Migration stance                                                                                                                                                                                                                                                         |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Public APIs       | Preserve request paths, headers, query strings, response shapes, and webhook signatures consumed by `packages/node-client`, `packages/frontend`, and `packages/connect-ui`.                                                                                              |
| CLI deploy/config | Preserve `nango.yaml` parsing, deploy payloads, generated artifacts, and server-side validation semantics. The TypeScript `packages/nango-yaml` package remains for the CLI; the Python backend needs a compatible parser/validator for the same parsed contract.        |
| Internal services | Preserve service RPC contracts between `server`, `jobs`, `runner`, `persist`, `orchestrator`, `scheduler`, and `metering` until each boundary is intentionally migrated.                                                                                                 |
| Usage/metering    | In scope. Preserve usage pubsub event shapes and usage storage contracts.                                                                                                                                                                                                |
| Billing           | Out of scope. Stripe, Orb, subscription/customer billing event payloads, and billing provider integrations are not Python core requirements.                                                                                                                             |
| Telemetry         | Out of scope. Do not add telemetry, tracing, metrics exporters, or BigQuery ingestion requirements as part of the Python core. Existing telemetry fields may need wire compatibility where already present in contracts, but they should not become new migration scope. |
| Logs              | Prefer Postgres-backed operational logs for the Python core. Elasticsearch should only be retained as optional compatibility for existing ES-backed log deployments.                                                                                                     |

## Contract sources

Most durable API shapes live in `@nangohq/types`, especially the `Endpoint<>` convention in `packages/types/lib/api.ts` and the endpoint union in `packages/types/lib/api.endpoints.ts`. Implementation packages then consume those types directly or indirectly:

- Public server routes: `packages/server/lib/routes.public.ts`.
- Public SDK: `packages/node-client/lib/index.ts`.
- Browser SDK: `packages/frontend/lib/index.ts`.
- Connect UI: `packages/connect-ui/src/lib/api.ts`, `packages/connect-ui/src/views/Go.tsx`.
- CLI deploy/config: `packages/cli/lib/**`, `packages/nango-yaml/lib/**`, `packages/types/lib/nangoYaml/index.ts`, `packages/types/lib/deploy/**`.
- Service contracts: `packages/orchestrator/lib/**`, `packages/scheduler/lib/**`, `packages/jobs/lib/**`, `packages/runner/lib/**`, `packages/persist/lib/**`.
- Pubsub contracts: `packages/types/lib/pubsub/events.ts`, `packages/pubsub/lib/**`.
- Storage contracts: migrations under `packages/database/lib/migrations`, `packages/records/lib/db/migrations`, `packages/keystore/lib/db/migrations`, `packages/scheduler/lib/db/migrations`, and `packages/usage/lib/clickhouse/migrations`.
- Webhook contracts: `packages/types/lib/webhooks/api.ts`, `packages/webhooks/lib/**`, `packages/node-client/lib/index.ts`.

## 1. Public API contracts

### Shared API conventions

- Public API methods use bearer authorization. `packages/node-client/lib/index.ts` adds `Authorization: Bearer <secretKey>` and Nango execution context headers such as `Nango-Is-Sync`, `Nango-Is-Script`, and `Nango-Is-Dry-Run`.
- Public endpoint shapes are typed with `Endpoint<>` in `packages/types/lib/api.ts`.
- Preserve case-insensitive HTTP header handling. Several SDK methods send canonical names but route/type definitions use lower-case equivalents.

### `packages/node-client`

The `Nango` class in `packages/node-client/lib/index.ts` is the main server-side public SDK. Python core compatibility must preserve these visible API families:

| Family                 | Methods and endpoints                                                                                                                                                                                              | Primary type sources                       |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------ |
| Providers              | `GET /providers`, `GET /providers/:provider`                                                                                                                                                                       | `packages/types/lib/providers/api.ts`      |
| Integrations           | `GET /integrations`, `GET /integrations/:uniqueKey`, `POST /integrations`, `POST /integrations/quickstart`, `PATCH /integrations/:uniqueKey`, `DELETE /integrations/:providerConfigKey`                            | `packages/types/lib/integration/api.ts`    |
| Connections and tokens | `GET /connections`, `GET /connections/:connectionId`, `PATCH /connections/:connectionId`, `DELETE /connections/:connectionId`, `POST /connections/metadata`, `PATCH /connections/metadata`                         | `packages/types/lib/connection/api/get.ts` |
| Records                | `GET /records`, `PATCH /records/prune`; headers include `Connection-Id` and `Provider-Config-Key`; query includes `model`, `variant`, `modified_after` or `delta`, `limit`, `filter`, `cursor`, and repeated `ids` | `packages/types/lib/record/api.ts`         |
| Syncs                  | `POST /sync/trigger`, `/sync/start`, `/sync/pause`, `/sync/status`, `/sync/update-connection-frequency`, `/sync/:name/variant/:variant`                                                                            | `packages/types/lib/sync/api.ts`           |
| Actions                | `POST /action/trigger`, `GET /action/:id`; async actions use `X-Async` and may return `AsyncActionResponse`                                                                                                        | `packages/types/lib/action/api.ts`         |
| Proxy                  | `/proxy/:endpoint` with Nango proxy headers such as `Connection-Id`, `Provider-Config-Key`, `Base-Url-Override`, `Nango-Proxy-*`, `Retries`, `Decompress`, `Retry-On`, `Forward-Headers-On-Redirect`               | `packages/node-client/lib/index.ts`        |
| Connect sessions       | `POST /connect/sessions`, `POST /connect/sessions/reconnect`                                                                                                                                                       | `packages/types/lib/connect/api.ts`        |

The client also exports webhook body types and verification helpers:

- `NangoAuthWebhookBody`, `NangoSyncWebhookBody`, and `NangoWebhookBody` are re-exported from `packages/node-client/lib/types.ts`.
- `verifyIncomingWebhookRequest(body, headers)` validates `X-Nango-Hmac-Sha256` using HMAC-SHA256 with the environment secret key.
- Deprecated `verifyWebhookSignature(signature, jsonPayload)` validates the legacy `X-Nango-Signature` SHA256 of `secret + payload`. Keep compatibility only while customers may still use it.

### `packages/frontend`

`packages/frontend/lib/index.ts` exposes the browser `Nango` SDK. Preserve:

- Constructor options: `host`, `websocketsPath`, `width`, `height`, `debug`, plus either `connectSessionToken` or `publicKey`.
- Unauthenticated connection creation: `POST /auth/unauthenticated/:providerConfigKey`.
- OAuth popup URL: `/oauth/connect/:providerConfigKey`.
- Custom credential auth URLs: `/auth/two-step/:providerConfigKey`, `/auth/signature/:providerConfigKey`, `/auth/bill/:providerConfigKey`, `/api-auth/api-key/:providerConfigKey`, `/api-auth/basic/:providerConfigKey`, `/auth/jwt/:providerConfigKey`, `/app-store-auth/:providerConfigKey`, `/auth/tba/:providerConfigKey`, `/oauth2/auth/:providerConfigKey`, and `/auth/oauth-outbound/:providerConfigKey`.
- Query parameters produced by the SDK: `connection_id`, `public_key`, `connect_session_token`, `params[...]`, `hmac`, `user_scope`, `credentials[oauth_*_override]`, `token_id`, `token_secret`, and `authorization_params[...]`.
- WebSocket message contract from `packages/frontend/lib/authModal.ts`: `connection_ack`, `error`, and `success`.
- Managed Connect UI iframe wrapper in `packages/frontend/lib/connectUI.ts`: parent sends `{ type: 'session_token' }`; UI emits `ready`, `close`, `connect`, `error`, and `settings_changed`.

### `packages/connect-ui`

`packages/connect-ui` is a React app that consumes `@nangohq/frontend` and `@nangohq/types`.

- Routes are defined in `packages/connect-ui/src/lib/routes.ts`: `/`, `/integrations`, `/go`.
- API helper in `packages/connect-ui/src/lib/api.ts` sends `Authorization: Bearer <sessionToken>`.
- Direct REST calls:
    - `GET /connect/session`
    - `GET /integrations`
    - `GET /providers/:provider`, optionally with `accept-language`
- `packages/connect-ui/src/lib/nango.ts` creates `Nango({ connectSessionToken, host: apiURL })`.
- `packages/connect-ui/src/views/Go.tsx` calls `nango.create()` for `auth_mode === 'NONE'` and `nango.auth()` for OAuth, custom credentials, app, and install flows.
- Parent postMessage events are emitted in `packages/connect-ui/src/lib/events.ts`: `ready`, `close`, `connect`, and `error`.
- `POST /connect/telemetry` exists in `packages/connect-ui/src/lib/telemetry.ts`, but telemetry is out of scope for Python core requirements.

## 2. CLI deploy and config contracts

### YAML parser and schema

`packages/nango-yaml` is the canonical TypeScript parser used by the CLI:

- `packages/nango-yaml/lib/load.ts` loads `nango.yaml` with `js-yaml`, detects v1/v2, and chooses the parser.
- `packages/nango-yaml/lib/parser.v2.ts` maps integrations, syncs, actions, on-events, post-connection scripts, scopes, endpoints, webhook subscriptions, input, and output.
- `packages/nango-yaml/lib/parser.ts` enforces semantic validation such as duplicate endpoints, duplicate models, missing sync output `id`, endpoint model references, and anonymous model warnings.
- `packages/nango-yaml/lib/modelsParser.ts` parses optional fields, `__extends`, `__string`, arrays, unions, native types, and aliases.
- Parsed TypeScript shapes live in `packages/types/lib/nangoYaml/index.ts`.

The Python backend needs a compatible parser/validator for backend-side deploy validation and migration tooling. The TypeScript package remains the CLI parser.

### CLI schema and commands

- CLI AJV schema validation lives in `packages/cli/lib/services/config.service.ts`.
- JSON schemas are `packages/cli/lib/nango.yaml.schema.v1.json` and `packages/cli/lib/nango.yaml.schema.v2.json`.
- `nango deploy [environment]` is defined in `packages/cli/lib/index.ts`; options include `--version`, `--sync`, `--action`, `--integration`, and `--allow-destructive`.
- Current deploy enforces Zero YAML through `packages/cli/lib/services/verification.service.ts`.

### Deploy endpoints and payloads

- Public routes are registered in `packages/server/lib/routes.public.ts`: `/sync/deploy`, `/sync/deploy/confirmation`, and `/sync/deploy/internal`.
- Shared deploy API types live in `packages/types/lib/deploy/api.ts`.
- `CLIDeployFlowConfig` is defined in `packages/types/lib/deploy/incomingFlow.ts` and includes function type, models, runs, auto-start, metadata, endpoints, delete tracking, integration key, input, script body, version, sync type, webhook subscriptions, JSON schema models, and features.
- Server deploy validation lives in `packages/server/lib/controllers/sync/deploy/validation.ts` and must remain compatible with CLI payloads.
- Zero YAML compile writes `.nango/nango.json` through `packages/cli/lib/services/model.service.ts` and bundles function code from `packages/cli/lib/zeroYaml/compile.ts`.
- `packages/cli/lib/zeroYaml/deploy.ts` posts first to `/sync/deploy/confirmation`, then to `/sync/deploy`; deploy payloads include bundled JS and source TS per function.

## 3. Internal service contracts

### Service responsibilities

| Service        | Contract responsibility                                                                                                                                                                                       |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `server`       | Public API facade. It schedules actions, syncs, webhooks, and on-event work through the orchestrator client.                                                                                                  |
| `orchestrator` | HTTP API over scheduler state. Owns task and recurring schedule RPCs.                                                                                                                                         |
| `scheduler`    | Postgres-backed task and schedule state machine. Owns dequeue, heartbeat, retries, concurrency, and schedule state.                                                                                           |
| `jobs`         | Coordinates work. It long-polls orchestrator, prepares execution context, selects runtime, starts runner or Lambda execution, receives results, records side effects, and updates orchestrator.               |
| `runner`       | Executes JS/TS customer functions. It does not coordinate system work; it receives code plus `NangoProps`, runs customer code, heartbeats to jobs, and sends final output back to jobs.                       |
| `runner-sdk`   | Available inside customer functions through the injected `nango` object. Runner constructs SDK-backed sync/action runners that expose records, checkpoints, logging, proxy, and helper APIs to function code. |
| `persist`      | HTTP service for records, checkpoints, and persistence operations used by runner SDK and jobs.                                                                                                                |
| `metering`     | Consumes usage/team pubsub events and writes usage/metering storage. Usage is in scope; billing provider behavior is not.                                                                                     |

### Orchestrator and scheduler

The orchestrator HTTP contract is implemented in `packages/orchestrator/lib/routes/v1/**` and wrapped by `packages/orchestrator/lib/clients/client.ts`.

| Endpoint                           | Contract                                                                                                                                                                  |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /v1/immediate`               | Create immediate task. Body includes `name`, optional `ownerKey`, optional concurrency group, retry settings, timeouts, and typed `args`. Returns `{ taskId, retryKey }`. |
| `POST /v1/recurring`               | Create recurring schedule. Body includes `name`, `state`, `startsAt`, `frequencyMs`, group/retry/timeouts, and sync args. Returns `{ scheduleId }`.                       |
| `POST /v1/dequeue`                 | Long-poll task dequeue with `{ groupKeyPattern, limit, longPolling }`.                                                                                                    |
| `POST /v1/tasks/:taskId/heartbeat` | Update task heartbeat.                                                                                                                                                    |
| `PUT /v1/tasks/:taskId`            | Complete task with `{ output, state: 'SUCCEEDED' \| 'FAILED' \| 'CANCELLED', nextExecutionInMs? }`.                                                                       |

Task payload validation is in `packages/orchestrator/lib/clients/validate.ts`:

- `sync`: `syncId`, `syncName`, `syncVariant`, `debug`, `connection`.
- `action`: `actionName`, `activityLogId`, `input`, `async`, `connection`.
- `webhook`: `webhookName`, `parentSyncName`, `activityLogId`, `input`, `connection`.
- `on-event`: `onEventName`, `version`, `fileLocation`, `sdkVersion`, `activityLogId`, `connection`.
- `abort` and sync abort shapes.

Scheduler persistence types are in `packages/scheduler/lib/types.ts`. Scheduler DB migrations under `packages/scheduler/lib/db/migrations` define `tasks` and `schedules`. The orchestrator uses Postgres `LISTEN/NOTIFY` channel `nango_task_events` in `packages/orchestrator/lib/events.ts`.

### Jobs and runner

`jobs` owns coordination; `runner` owns customer JS/TS execution.

- Jobs processor loop: `packages/jobs/lib/processor/processor.ts`, `packages/jobs/lib/processor/handler.ts`.
- Runner tRPC methods: `health`, `start`, `abort`, and `notifyWhenIdle` in `packages/runner/lib/server.ts`.
- Runner `start` params: `{ taskId, nangoProps, code, codeParams? }`.
- Shared execution context `NangoProps`: `packages/types/lib/runner/sdk.ts`.
- Runner execution path: `packages/runner/lib/exec.ts`; it runs CommonJS-wrapped code in `node:vm` and calls the default export for actions, syncs, webhooks, and on-events.
- Runner SDK bridge: `packages/runner/lib/sdk/sdk.ts`, backed by `@nangohq/runner-sdk`.
- Runner result callback to jobs: `PUT /tasks/:taskId` in `packages/types/lib/jobs/api.ts` with `nangoProps?`, `error?`, `output?`, `telemetryBag`, `functionRuntime`, and `checkpoints?`.
- Runner heartbeat callback to jobs: `POST /tasks/:taskId/heartbeat` in `packages/types/lib/jobs/api.ts`; jobs forwards to orchestrator.

`telemetryBag` and tracing references are existing wire fields, not new Python telemetry scope.

### Persist service

- Persist server setup: `packages/persist/lib/server.ts`, `packages/persist/lib/app.ts`.
- Environment-scoped auth path: `/environment/:environmentId/*`.
- Records path prefix: `/environment/:environmentId/connection/:nangoConnectionId/sync/:syncId/job/:syncJobId/records`.
- Record mutations accept `{ model, records, providerConfigKey, connectionId, activityLogId, merging }` and return `{ nextMerging }`.
- Merging strategy types live in `packages/types/lib/record/api.ts`.

### Webhook dispatch queue

Provider webhooks may be queued to jobs. `packages/jobs/lib/webhook/dispatch-queue/consumer.ts` consumes SQS messages shaped as:

- `version: 1`
- `kind: 'webhook'`
- `taskName`
- `accountId`
- `integrationId`
- `provider`
- `parentSyncName`
- `activityLogId`
- `webhookName`
- `connection`
- `payload`

Jobs converts the message into orchestrator webhook tasks.

## 4. Pubsub event contracts

The pubsub event envelope is defined in `packages/types/lib/pubsub/events.ts`:

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

Publishers fill missing `idempotencyKey` and `createdAt` in `packages/pubsub/lib/publisher.ts`.

Transport details:

- ActiveMQ topic path: `/topic/VirtualTopic.${event.subject}`.
- ActiveMQ consumer queue: `/queue/Consumer.${consumerGroup}.VirtualTopic.${subject}`.
- SNS/SQS uses `topicArns[event.subject]`, SQS subscription key `${consumerGroup}:${subject}`, message attribute `subject`, and v8-serialized base64 payloads.
- Transport selection comes from `NANGO_PUBSUB_TRANSPORT` in `packages/pubsub/lib/transport/default.ts`.

Current event types:

| Subject | Type                           | Payload notes                                                                                                                                |
| ------- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `user`  | `user.created`                 | `{ userId, teamId }`                                                                                                                         |
| `team`  | `team.updated`                 | `{ id }`; consumed by metering team processor                                                                                                |
| `usage` | `usage.records`                | Common usage properties plus `syncId`, `model`                                                                                               |
| `usage` | `usage.monthly_active_records` | Common usage properties plus `syncId`, `model`                                                                                               |
| `usage` | `usage.actions`                | Common usage properties plus `actionName`                                                                                                    |
| `usage` | `usage.connections`            | Common usage properties                                                                                                                      |
| `usage` | `usage.function_executions`    | Common usage properties plus `type`, `success`, `functionName`, optional `runtime`, optional existing `telemetryBag`, optional `frequencyMs` |
| `usage` | `usage.proxy`                  | Common usage properties plus `success`                                                                                                       |
| `usage` | `usage.webhook_forward`        | Common usage properties plus `success`                                                                                                       |

The metering usage consumer group is currently named `billing` in `packages/metering/lib/processors/usage.ts`. Treat that name as legacy coupling: usage/metering remains in scope, billing integrations and billing events do not.

## 5. Database and storage contracts

### App database

Primary app DB migrations live in `packages/database/lib/migrations`. Core tables to freeze for Python core compatibility:

| Area                            | Tables and references                                                        |
| ------------------------------- | ---------------------------------------------------------------------------- |
| Accounts/users/environments     | `_nango_accounts`, `_nango_users`, `_nango_environments`, `_nango_db_config` |
| Integration config              | `_nango_configs`                                                             |
| Connections                     | `_nango_connections`                                                         |
| OAuth/auth sessions             | `_nango_oauth_sessions`                                                      |
| Sync/function config and jobs   | `_nango_sync_configs`, `_nango_syncs`, `_nango_sync_jobs`                    |
| Connect sessions/end users      | tables from `20240925173951_create_connect_session.cjs`                      |
| Active operational log pointers | `_nango_active_logs` from `20240527094039_add_notifications_table.cjs`       |
| Account usage                   | `accounts_usage` from `20250717153012_create_accounts_usage_table.cjs`       |

Legacy `_nango_sync_schedules` was dropped in `20250314113254_drop_schedules.cjs`; scheduler package tables are the source of truth for schedules.

### Records database

Records storage is defined by `packages/records/lib/constants.ts` and migrations under `packages/records/lib/db/migrations`:

- `records`: partitioned by `(connection_id, model)`, with `id`, `external_id`, JSON metadata, data hash, connection/model keys, timestamps, delete/sync metadata, and unique constraints on `(connection_id, model, external_id)` and `(connection_id, model, id)`.
- `records_data`: split JSONB blob/data table, partitioned by `(connection_id, model)`, primary key `(connection_id, model, id)`.
- `record_counts`: per environment/connection/model counts plus `size_bytes`.

### Keystore

`packages/keystore/lib/db/migrations/20240920184658_initial_keystore_model.ts` defines `private_keys`:

- encrypted and hashed private keys
- scoped by account, environment, and entity
- entity enum: `session`, `connection`, `environment`
- expiry and access timestamps

Model behavior and encryption format are in `packages/keystore/lib/models/privatekeys.ts`.

### Logs

- ES-backed logs are defined in `packages/logs/lib/es/schema.ts` and should be treated as optional compatibility for existing deployments.
- Old Postgres activity log tables were created in `20230510083713_activity_logging_table.cjs` and dropped in `20240626144305_active_logs_drop.cjs`.
- Python core should prefer Postgres-backed operational logs. Existing `_nango_active_logs` stores active error/log references by type, action, connection, log id, active flag, and sync id.

### Scheduler database

Scheduler DB migrations under `packages/scheduler/lib/db/migrations` define:

- `tasks`: UUID task id, name, payload JSON, group key, retry counters, timeout fields, state, heartbeat, output, termination, retry key, owner key, and group max concurrency.
- `schedules`: UUID schedule, name, state, starts/frequency, payload, timestamps, deleted flag, task FK, last scheduled task state, and next execution time.

### Usage and metering storage

Usage/metering is in scope:

- `accounts_usage` Postgres table stores monthly per-account `actions` and `active_records`.
- ClickHouse raw usage table `raw_events(ts, idempotency_key, type, account_id, value, attributes)` has a 90-day TTL.
- ClickHouse daily aggregate tables include `daily_mar`, `daily_records`, `daily_actions`, `daily_function_executions`, `daily_proxy`, and `daily_connections`.

Billing storage and external billing provider contracts are out of scope.

## 6. Webhook payload and signature contracts

Webhook body types live in `packages/types/lib/webhooks/api.ts`; delivery code lives in `packages/webhooks/lib/**`.

### Outgoing Nango webhooks

All outgoing Nango webhooks are POSTed as stable-stringified JSON. `packages/webhooks/lib/utils.ts` sends:

- `X-Nango-Hmac-Sha256`: HMAC-SHA256 over the stable JSON body using the environment webhook signing secret.
- `X-Nango-Signature`: deprecated SHA256 of `secret + payload`, kept for backwards compatibility.
- `content-type: application/json`.
- Nango user agent.

`deliver()` filters non-forwardable inbound headers before forwarding provider webhook headers.

Payload types:

| Type           | Source                                 | Contract                                                                                                                                                                                                                                                                                         |
| -------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `sync`         | `packages/webhooks/lib/sync.ts`        | Base fields: `from: 'nango'`, `type: 'sync'`, `connectionId`, `providerConfigKey`, `syncName`, `syncVariant`, `model`, optional `checkpoints`, deprecated `syncType`. Success adds `modifiedAfter`, `responseResults`, deprecated `queryTimeStamp`. Error adds `error`, `startedAt`, `failedAt`. |
| `auth`         | `packages/webhooks/lib/auth.ts`        | Base fields: `from: 'nango'`, `type: 'auth'`, `connectionId`, `providerConfigKey`, `authMode`, `provider`, `environment`, `operation`, optional tags and end-user. Success has `success: true`; failure has `success: false` plus `error`.                                                       |
| `async_action` | `packages/webhooks/lib/asyncAction.ts` | `from: 'nango'`, `type: 'async_action'`, `connectionId`, `providerConfigKey`, and `payload: { id, statusUrl }`.                                                                                                                                                                                  |
| `forward`      | `packages/webhooks/lib/forward.ts`     | If routed to connections, body includes `from: <provider>`, `type: 'forward'`, `providerConfigKey`, `connectionId`, and `payload`. If no connection ids are resolved, the original provider payload is forwarded directly for compatibility.                                                     |

Webhook environment settings are patched through `PATCH /api/v1/environments/webhook` in `packages/types/lib/environment/api/webhook.ts`, with flags such as `on_sync_completion_always`, `on_auth_creation`, `on_auth_refresh_error`, `on_sync_error`, and `on_async_action_completion`.

### Incoming provider webhooks

Provider webhook routing is implemented by `packages/server/lib/webhook/webhook.manager.ts` and provider-specific routing scripts in `packages/server/lib/webhook/*-webhook-routing.ts`.

- Handlers receive `headers`, parsed `body`, `rawBody`, and optional `query`.
- Successful route results may include `connectionIds` and `toForward`.
- If forwarding is enabled and not capped, Nango forwards the provider webhook to customer webhook URLs and emits `usage.webhook_forward`.

## First-pass golden fixtures and contract tests

Create fixtures before starting Python implementation. Suggested first pass:

### Public API fixtures

- [ ] Node client request fixtures for providers, integrations, connections, metadata, records, sync control, action trigger/result, proxy, and connect sessions.
- [ ] Header canonicalization fixtures for `Connection-Id`, `Provider-Config-Key`, `X-Async`, proxy headers, and bearer auth.
- [ ] Record listing fixtures covering `delta`, `modified_after`, `ids[]`, pagination cursor, model variants, and prune response.
- [ ] Connect session fixtures for create, reconnect, and session read.
- [ ] Browser SDK auth URL fixtures for OAuth and each custom credential URL family.
- [ ] Connect UI postMessage fixtures for `ready`, `close`, `connect`, `error`, `settings_changed`, and OAuth callback ack/error/success messages.

### CLI and YAML fixtures

- [ ] `nango.yaml` v1 and v2 parser fixtures with parsed `NangoYamlParsed` JSON snapshots.
- [ ] Model parser fixtures for optional fields, arrays, unions, `__extends`, `__string`, native types, aliases, and invalid anonymous model cases.
- [ ] Duplicate endpoint/model and missing sync output `id` validation fixtures.
- [ ] Deploy confirmation and deploy request/response fixtures for zero YAML with source TS plus bundled JS.
- [ ] Server deploy validation fixtures for `models_json_schema.definitions`, input/output models, webhook subscriptions, features, and destructive reconciliation.

### Internal service fixtures

- [ ] Orchestrator `POST /v1/immediate`, `POST /v1/recurring`, `POST /v1/dequeue`, heartbeat, and complete-task fixtures.
- [ ] Scheduler DB state fixtures for task lifecycle, retry, timeout, owner key, retry key, group concurrency, and recurring schedule execution.
- [ ] Jobs dispatch fixtures for `sync`, `action`, `webhook`, `on-event`, and `abort` payloads.
- [ ] Runner tRPC `start`, `abort`, and `notifyWhenIdle` fixtures.
- [ ] Jobs callback fixtures for runner result and heartbeat endpoints.
- [ ] Persist record mutation fixtures for save, update, delete, merge strategy, checkpoints, and response `{ nextMerging }`.

### Pubsub and storage fixtures

- [ ] Pubsub envelope fixtures for generated and caller-provided `idempotencyKey` and `createdAt`.
- [ ] Transport serialization fixtures for ActiveMQ topic/queue names and SNS/SQS v8-base64 payloads.
- [ ] Usage event fixtures for records, MAR, actions, connections, function executions, proxy, and webhook forwards.
- [ ] App DB migration smoke fixtures for accounts, environments, integrations, connections, OAuth sessions, sync configs, syncs, sync jobs, connect sessions, active logs, and account usage.
- [ ] Records DB fixtures for partition keys, unique constraints, record counts, deletes, and `records_data` split storage.
- [ ] Keystore fixtures for entity scoping, encryption format, hashing, expiry, and access timestamps.
- [ ] Scheduler DB fixtures for tasks and schedules.
- [ ] Usage/metering storage fixtures for Postgres `accounts_usage`, ClickHouse raw events, and daily aggregates.

### Webhook fixtures

- [ ] Stable JSON stringification and `X-Nango-Hmac-Sha256` signature fixtures.
- [ ] Deprecated `X-Nango-Signature` compatibility fixture.
- [ ] `sync` success, no-change suppression, failure, checkpoints, deprecated `syncType`, and deprecated `queryTimeStamp` fixtures.
- [ ] `auth` creation, refresh error, override, tags, and end-user fixtures.
- [ ] `async_action` completion fixture.
- [ ] `forward` fixture with resolved connection ids and fixture with direct original payload forwarding when no connection ids are resolved.
- [ ] Incoming provider webhook routing fixtures that preserve `rawBody`, query, headers, `toForward`, and `connectionIds`.

## Open migration follow-ups

Cutover topology is resolved: Python will replace the TypeScript backend in one coordinated release after offline parity and full-system readiness. No TypeScript facade, production shadowing, canary, or traffic split is planned.

- Define exact golden fixture storage location and update test runners before writing Python code.
- Split billing-specific code paths from usage/metering where legacy names such as the `billing` consumer group are only incidental.
- Decide the target Postgres operational log schema before replacing any ES-backed log read/write path.
