# Contract: GET /integrations/:uniqueKey

Authoritative TypeScript sources frozen for this boundary. Cite these when in doubt; do not infer behavior from tests alone.

## Source of truth

| Concern | TypeScript file |
|---|---|
| Route wiring | `packages/server/lib/routes.public.ts:192` (`apiAuth`, `withAnyScope('environment:integrations:read','environment:integrations:read_credentials')`) |
| Handler | `packages/server/lib/controllers/integrations/uniqueKey/getIntegration.ts` |
| Auth middleware | `packages/server/lib/middleware/access.middleware.ts` (`secretKeyAuth`) |
| Scope middleware | `packages/server/lib/middleware/scope.middleware.ts` (`hasScope`, `withAnyScope`) |
| Account context lookup | `packages/shared/lib/services/account.service.ts` (`getAccountContextByApiKey`, `getAccountContextByCustomerKey`, `getAccountContextByInternalSecret`) |
| Customer key service | `packages/shared/lib/services/customerKey.service.ts` |
| Encryption | `packages/utils/lib/encryption.ts` (`Encryption`), `packages/shared/lib/utils/encryption.manager.ts` (`decryptAPISecret`) |
| Error envelope | `packages/shared/lib/utils/error.manager.ts` (`errRes`, `errResFromNangoErr`), `packages/shared/lib/utils/error.ts` (`NangoError`) |
| Response formatter | `packages/server/lib/formatters/integration.ts` (`integrationToPublicApi`) |
| Provider catalog | `packages/providers/lib/index.ts` (`getProvider`, `getProviders`) |
| Integration repo | `packages/shared/lib/services/config.service.ts` (`getProviderConfig`) |
| Types | `packages/types/lib/integration/api.ts` (`GetPublicIntegration`, `ApiPublicIntegration`, `ApiPublicIntegrationInclude`), `packages/types/lib/integration/db.ts` (`IntegrationConfig`), `packages/types/lib/environment/db.ts` (`DBEnvironment`, `DBAPISecret`, `DBCustomerKey`) |
| Param validation | `packages/server/lib/helpers/validation.ts` (`providerConfigKeySchema`) |
| Query error shape | `packages/utils/lib/express/validate.ts` (`zodErrorToHTTP`) |

## Request

```
GET /integrations/:uniqueKey
Authorization: Bearer <secret-key-uuid-v4>
Nango-Is-Script: true|false   (optional; default false)
?include=webhook&include=credentials   (optional; single or repeated)
```

- `uniqueKey` must match `^[a-zA-Z0-9~:.@ _-]+$` and be ≤255 chars.
- Bearer token must be UUID v4 (`/^[0-9A-F]{8}-[0-9A-F]{4}-[4][0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$/i`).
- `Nango-Is-Script: true` routes the token through `internalSecretKey` (api_secrets) lookup instead of `secretKey` (customer_keys) lookup.

## Authentication flow (fail closed)

1. No `Authorization` header → 401 `missing_auth_header`.
2. `Bearer ` split yields empty → 401 `malformed_auth_header`.
3. Token fails UUID v4 regex → 401 `invalid_secret_key_format`.
4. `accountService.getAccountContextByApiKey({ secretKey|internalSecretKey })` returns null → 401 `unknown_account`.
5. `flagHasPlan && !plan` → 401 `plan_not_found` (out of scope for this slice; plan checks are billing).

Auth error envelope (from `NangoError` + `errResFromNangoErr`):

```json
{ "error": { "message": "<message>", "code": "<code>", "payload": {} } }
```

`additional_properties` is `undefined` for these codes and omitted from JSON.

Messages:
- `missing_auth_header`: "Authentication failed. The request is missing the Authorization header."
- `malformed_auth_header`: "Authentication failed. The Authorization header is malformed."
- `invalid_secret_key_format`: "Authentication failed. The provided secret key is not a UUID v4."
- `unknown_account`: "Authentication failed. The provided authorization header does not match any account."

## Authorization (scope)

`withAnyScope('environment:integrations:read', 'environment:integrations:read_credentials')`.

`hasScope({ grantedScopes, requiredScope })`:
- `grantedScopes` undefined → false.
- exact `s === requiredScope` → true.
- `s.endsWith(':*')` && `requiredScope.startsWith(s.slice(0, -1))` → true. So `environment:*` matches both required scopes.

Fail → 403:
```json
{ "error": { "code": "forbidden", "message": "Insufficient scope. Required one of: environment:integrations:read or environment:integrations:read_credentials" } }
```

Scope sources:
- `customer_key` auth: `row.auth_scopes ?? []` from `customer_keys.scopes` (default `['environment:*']` on creation).
- `api_secret` (internal) auth: `['environment:*']`.
- `env_var` auth: `['environment:*']`.

## Handler flow

1. Validate query (`include` optional, enum `['webhook','credentials']`, single or array). Invalid → 400 `invalid_query_params` with `{ error: { code, errors: [{code, message, path}] } }`.
2. Validate params (`uniqueKey`). Invalid → 400 `invalid_uri_params` with same errors shape.
3. If `include.size > 0` and `authType !== 'secretKey'` → 403 `invalid_permissions` "Can't include credentials without a private key".
4. `configService.getProviderConfig(uniqueKey, environment.id)` — selects `_nango_configs` where `unique_key=:uniqueKey AND environment_id=:envId AND deleted=false`, left joins `providers_shared_credentials`, decrypts `oauth_client_secret`/`custom`. Null → 404 `not_found` `Integration "<uniqueKey>" does not exist`.
5. `getProvider(integration.provider)` from `providers.yaml`. Null → 404 `not_found` `Unknown provider <provider>`.
6. Build `include`:
   - `webhook_url`: if `webhook` requested — `${getGlobalWebhookReceiveUrl()}/${environment.uuid}/${integration.provider}` when `provider.webhook_routing_script` exists, else `null`.
   - `credentials`: if `credentials` requested AND `hasScope('environment:integrations:read_credentials')`:
     - `OAUTH1|OAUTH2|TBA`: `{ type, client_id: shared_credentials_id ? '' : oauth_client_id, client_secret: shared_credentials_id ? '' : oauth_client_secret, scopes: oauth_scopes || null, webhook_secret: custom?.webhookSecret || null }`
     - `APP`: `{ type, app_id: oauth_client_id, private_key: oauth_client_secret, app_link: app_link || null }`
     - else: `null`
   - If `credentials` requested but scope missing, `credentials` key is omitted (not null).
7. Response 200 `{ data: integrationToPublicApi(...) }`:

```json
{
  "data": {
    "unique_key": "<uniqueKey>",
    "provider": "<provider>",
    "display_name": "<integration.display_name || provider.display_name>",
    "logo": "<basePublicUrl>/images/template-logos/<provider>.svg",
    "forward_webhooks": true,
    "created_at": "<ISO 8601 UTC>",
    "updated_at": "<ISO 8601 UTC>",
    "webhook_url": "<...|null>",     // only if include=webhook
    "credentials": { ... }           // only if include=credentials and scope held
  }
}
```

- `basePublicUrl` = `NANGO_PUBLIC_SERVER_URL` || `NANGO_SERVER_URL` || `http://localhost:3003`.
- `forward_webhooks` defaults to true when undefined.
- `display_name` falls back to `provider.display_name` when integration field is null.

## DB tables touched

- `_nango_configs` (integration config; `unique_key`, `environment_id`, `provider`, `oauth_client_id`, `oauth_client_secret`, `oauth_scopes`, `app_link`, `custom`, `missing_fields`, `display_name`, `forward_webhooks`, `shared_credentials_id`, `deleted`, timestamps).
- `providers_shared_credentials` (optional left join).
- `customer_keys` + `customer_keys_relations` (customer-key auth).
- `api_secrets` (internal-secret auth; also joined for default/pending secret in all paths).
- `_nango_environments` + `_nango_accounts` (context resolution).
- `plans` (left join; billing — out of scope for this slice).

## Fixtures

Scenarios under `fixtures/get_by_key/`. Each fixture records request inputs and expected response status/body. Dynamic values (`<secret-key>`, timestamps, `environment.uuid`, `basePublicUrl`) are placeholders normalized by the differential harness.