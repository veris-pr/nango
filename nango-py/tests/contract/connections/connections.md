# Contract: connection reads

Authoritative TypeScript sources frozen for `GET /connections` (list) and
`GET /connections/:connectionId` (single). Cite these when in doubt.

## Source of truth

| Concern | TypeScript file |
|---|---|
| Route wiring | `packages/server/lib/routes.public.ts:200,202,223,228` |
| List handler | `packages/server/lib/controllers/connection/getConnections.ts` (`getPublicConnections`) |
| Single handler | `packages/server/lib/controllers/connection/connectionId/getConnection.ts` (`getPublicConnection`) |
| List formatter | `packages/server/lib/formatters/connection.ts` (`connectionSimpleToPublicApi`) |
| Single formatter | `packages/server/lib/formatters/connection.ts` (`connectionFullToPublicApi`) |
| End-user formatter | `packages/server/lib/formatters/endUser.ts` (`endUserToApi`) |
| Connection service | `packages/shared/lib/services/connection.service.ts` (`listConnections`, `getConnection`) |
| Encryption | `packages/shared/lib/utils/encryption.manager.ts` (`decryptConnection`) |
| Types | `packages/types/lib/connection/api/get.ts`, `packages/types/lib/connection/db.ts`, `packages/types/lib/endUser/index.ts` (`ApiEndUser`, `DBEndUser`) |
| Tag schema | `packages/shared/lib/services/tags/schema.ts` (`connectionTagsSchema`, `connectionTagsKeySchema`) |
| Param schemas | `packages/server/lib/helpers/validation.ts` (`connectionIdSchema`, `providerConfigKeySchema`) |
| stringbool | `node_modules/zod/v4` `_stringbool` |

## GET /connections (list)

Auth: `apiAuth, withAnyScope('environment:connections:list', 'environment:connections:list_credentials')`.

Query (`.strict()` — only these keys, else `invalid_query_params`):
- `connectionId?` string min 1 max 255
- `search?` string min 1 max 255
- `endUserId?` string (end-user id schema)
- `integrationId?` string min 1 — split on `,`, trimmed → `integrationIds[]`
- `endUserOrganizationId?` string (end-user id schema)
- `tags?` `connectionTagsSchema` — record `key→value`, keys `^[a-zA-Z][a-zA-Z0-9_\-./]*$` ≤64, values min 1 ≤255, max 10 keys, **keys lowercased**; edge: duplicate-after-lowercase and `end_user_email` email validation (deferred edge cases)
- `limit?` int 1–2000 (default 10000)
- `page?` int ≥0 (default 0)

Query param `tags` is passed as `tags[key]=value` (repeated); Express `qs` parses to a record, then zod lowercases keys.

Response `200`: **`{ connections: ApiPublicConnection[] }`** (key is `connections`, not `data`).

`ApiPublicConnection` (`connectionSimpleToPublicApi`, no credentials):
```json
{
  "id": <int>,
  "connection_id": "<str>",
  "provider_config_key": "<str>",
  "provider": "<str>",
  "errors": [{"type": "<str>", "log_id": "<str>"}, ...],
  "end_user": ApiEndUser | null,
  "tags": <object>,
  "metadata": <object> | null,
  "created": "<ISO 8601>"          // note: `created`, not `created_at`
}
```

`ApiEndUser`:
```json
{
  "id": "<end_user_id str>",
  "display_name": "<str>|null",
  "email": "<str>|null",
  "tags": <object>|null,
  "organization": {"id": "<str>", "display_name": "<str>|null"} | null
}
```

### listConnections dataflow

- CTE `filtered_connections`: `_nango_connections` where `environment_id` and `deleted=false`; filters:
  - `connection_id = :connectionId`
  - integrationIds: join `_nango_configs` on `config_id=id`, `unique_key IN (:integrationIds)`
  - tags: `_nango_connections.tags @> :tags::jsonb` (lowercased dict)
  - endUserId / endUserOrganizationId: leftJoin `end_users`, `end_users.end_user_id` / `end_users.organization_id`
  - search: leftJoin `end_users`; `(connection_id ILIKE %search% OR end_users.display_name ILIKE %search% OR end_users.email ILIKE %search%)`
  - order `created_at DESC`, `limit`, `offset(page*limit)`
- CTE `active_logs_agg`: `json_agg(json_build_object('type','log_id'))` from `_nango_active_logs` where `active=true` and `connection_id IN (filtered)`, group by `connection_id`
- Final join: `_nango_connections` innerJoin `filtered_connections` innerJoin `_nango_configs` (provider) leftJoin `end_users` leftJoin `active_logs_agg`; `COALESCE(active_logs_agg.active_logs, '[]'::json)`. Order `created_at DESC`.
- **No credential decryption on the list path** (list items never include credentials).

## GET /connections/:connectionId (single)

Auth: `apiAuth, withAnyScope('environment:connections:read', 'environment:connections:read_credentials')`.

Params: `connectionId` — `connectionIdSchema` `^[a-zA-Z0-9,.;:=+~[\]|@${}"'\\/_ -]+$` ≤255.
Query (`.strict()`):
- `provider_config_key` **required** — `providerConfigKeySchema` `^[a-zA-Z0-9~:.@ _-]+$` ≤255
- `refresh_token?` stringbool default false
- `force_refresh?` stringbool default false
- `refresh_github_app_jwt_token?` stringbool default false

stringbool: lowercased; truthy `{"true","1","yes","on","y","enabled"}` → true; falsy `{"false","0","no","off","n","disabled"}` → false; else `invalid_query_params`.

Flow:
1. `configService.getProviderConfig(provider_config_key, env.id)` → null → `400 unknown_provider_config "Provider does not exists"`.
2. `connectionService.getConnection(connectionId, providerConfigKey, env.id)` → not found → `404 not_found "Failed to find connection"`.
3. **Credential refresh / test** (`refreshOrTestCredentials`) — **DEFERRED to Phase 5 (auth flows)**. On refresh failure the TS returns `invalid_credentials` with a connection payload; we return stored credentials and do not refresh.
4. `includeCredentials = hasScope('environment:connections:read_credentials')`.
5. If `credentials.type === 'OAUTH2'` and `returnRefreshToken === false`: strip `refresh_token` from credentials (and from `credentials.raw`).
6. `connectionFullToPublicApi({data, provider, activeLog, endUser, includeCredentials})`.

Response `200`: **`ApiPublicConnectionFull`** (top-level object, not wrapped in `data`):
```json
{
  "id": <int>,
  "connection_id": "<str>",
  "provider_config_key": "<str>",
  "provider": "<str>",
  "errors": [{"type","log_id"}, ...],
  "end_user": ApiEndUser | null,
  "tags": <object>,
  "metadata": <object>|null,
  "connection_config": <object>,      // defaults to {} when null
  "created_at": "<ISO>",
  "updated_at": "<ISO>",
  "last_fetched_at": "<ISO>|null",
  "credentials": <AllAuthCredentials>   // full if read_credentials scope, else {}
}
```

Note: credentials is `{}` (empty object) when scope absent — **not** redacted (unlike the private v1 API).

### getConnection dataflow

`_nango_connections` where `connection_id`, `provider_config_key`, `environment_id`, `deleted=false` LIMIT 1. `decryptConnection`: if `credentials.encrypted_credentials` + `credentials_iv` + `credentials_tag` → `JSON.parse(decryptSync(...))`; else use stored `credentials`. Parse `expires_at` if present.

For the single response the TS re-runs `listConnections({connectionId, integrationIds:[providerConfigKey]})` to fetch `end_user`/`active_logs`/`provider`, then merges decrypted credentials. We replicate by querying connection + end_user + active_logs + provider in one go.

## DB tables

- `_nango_connections`: id, provider_config_key, connection_id, credentials (json `{encrypted_credentials?}`), connection_config (jsonb), metadata (jsonb), credentials_iv/credentials_tag (varchar), environment_id, config_id, end_user_id (int FK→end_users), last_fetched_at, credentials_expires_at, last_refresh_success/failure, refresh_attempts (smallint), refresh_exhausted (bool), last_execution_at, tags (jsonb), deleted, deleted_at, created_at, updated_at.
- `end_users`: id, end_user_id (varchar external id), account_id, environment_id, email, display_name, organization_id, organization_display_name, tags (json), created_at, updated_at.
- `_nango_active_logs`: id, type, action, connection_id (int FK), activity_log_id, log_id, active (bool), sync_id, timestamps.
- `_nango_configs`: provider (joined for the `provider` field), unique_key (for integrationId filter).

## Deferred from this slice (tracked, not blocking)

- Credential refresh / token refresh / github-app JWT / `invalid_credentials` error → Phase 5 (auth flows).
- Tag edge-case validation: `end_user_email` email check, duplicate-key-after-lowercase → note; functional core (max 10, key regex, lowercase normalize) is implemented.
- Connect-session auth path (Connect UI) → Phase 2 follow-up.