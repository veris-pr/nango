# Contract: proxy

Authoritative TypeScript sources for `/proxy/*splat` (all methods). This is the
largest read/write boundary: outbound HTTP with credential injection, retries,
redirects, and decompression. Cite these when in doubt.

## Source of truth

| Concern | TypeScript file |
|---|---|
| Route wiring | `packages/server/lib/routes.public.ts:291` (`apiAuth`, `withScope('environment:proxy')`, `upload.any()`, `allPublicProxy`) |
| Handler | `packages/server/lib/controllers/proxy/allProxy.ts` (`allPublicProxy`, `parseHeaders`, `handleResponse`, `handleErrorResponse`) |
| Retry loop | `packages/shared/lib/services/proxy/request.ts` (`ProxyRequest.request`) |
| Config + URL + headers | `packages/shared/lib/services/proxy/utils.ts` (`getProxyConfiguration`, `buildProxyURL`, `buildProxyHeaders`, `getAxiosConfiguration`, `ProxyError`, `RetryReason`) |
| Retry decision | `packages/shared/lib/services/proxy/retry.ts` (`getProxyRetryFromErr`, `getRetryFromHeader`, `getRetryFromBody`, `parseRetryValue`, `matchesStatusCode`) |
| Base URL denylist | `packages/server/lib/controllers/proxy/baseUrlOverrideDenylist.ts` |
| Connection lookup | `packages/shared/lib/services/connection.service.ts` (`getConnection`) |
| Credential refresh | `packages/shared/lib/services/connections/credentials/refresh.ts` (`refreshOrTestCredentials`) — **deferred to Phase 5** |
| Types | `packages/types/lib/proxy/api.ts` (`AllPublicProxy`, `ApplicationConstructedProxyConfiguration`, `ConnectionForProxy`, `IntegrationConfigForProxy`, `UserProvidedProxyConfiguration`) |

## Request

```
ANY /proxy/<endpoint>   (method preserved; endpoint = originalUrl with /^\/proxy\// → "/")
Authorization: Bearer <secret-key>     (apiAuth)
Headers (validated via schemaHeaders, all lowercase on the wire):
  provider-config-key: required (providerConfigKeySchema ^[a-zA-Z0-9~:.@ _-]+$ ≤255)
  connection-id:      required (connectionIdSchema)
  retries:            number, default 0
  base-url-override:  url | "" optional
  decompress:         "true" | "false" optional
  retry-on:           ^\d+(,\d+)* optional  (e.g. "429,503")
  forward-headers-on-redirect: "true" | "false", default "true"
  nango-activity-log-id: string ≤255 optional
  nango-is-sync:      "true" | "false" optional
  nango-is-dry-run:   "true" | "false" optional
Nango-Proxy-<X>: <value>   (forwarded headers; stripped of the Nango-Proxy- prefix)
Body: raw body (or multipart files via upload.any())
```

Invalid headers → `400 { error: { code: "invalid_headers", errors: [{code, message, path}] } }`.

## Handler flow

1. Validate `schemaHeaders` → `400 invalid_headers` on failure.
2. `base-url-override` denylist (env `NANGO_PROXY_BASE_URL_OVERRIDE_DENYLIST`) → `400 base_url_override_not_allowed "This base URL override is not allowed by server configuration."`.
3. **Plan capping** (`capping.getStatus(plan, 'proxy')`) → `402 plan_limit` — **billing, deferred**.
4. `method = req.method.toUpperCase()`; `endpoint = req.originalUrl.replace(/^\/proxy\//, '/')`.
5. `headers = parseHeaders(req)` → forwarded `Nango-Proxy-*` stripped to key (case preserved from raw header name).
6. `data = req.rawBody | req.body`; `files = req.files` (multipart).
7. `configService.getProviderConfig(providerConfigKey, env.id)` → null → `404 unknown_provider_config "Provider config not found for the given provider config key. Please make sure the provider config exists in the Nango dashboard."`.
8. `connectionService.getConnection(connectionId, providerConfigKey, env.id)` → error/null → `400 server_error "Failed to get connection"`.
9. **`refreshOrTestCredentials`** → on error: `connection_refresh_backoff` → its status; else `500 server_error "Failed to get connection credentials: '<msg>'"` — **refresh deferred; we use stored decrypted credentials**.
10. Build `InternalProxyConfiguration { providerName: integration.provider }`.
11. `getProxyConfiguration({ externalConfig, internalConfig })` → `ApplicationConstructedProxyConfiguration` (or `ProxyError`: `missing_api_url`, `missing_provider`, `unknown_provider`, `unsupported_provider`).
12. `new ProxyRequest({ proxyConfig, logger, getConnection (memoized 60s), getIntegrationConfig })`.
13. `proxy.request()` → success stream / axios error.
14. **handleResponse**: chunked/encoded/attachment → pass-through stream; else buffer (204 → end). Set `Content-Type`.
15. **handleErrorResponse**: `proxy_redirect_to_denied_host` → `400 base_url_override_not_allowed`; `ProxyError` → `400 {code, message}`; axios error → upstream `status` + `headers` + body passthrough (JSON parsed if content-type json).
16. Publish `usage.proxy` (success flag).

## getProxyConfiguration

- `endpoint` defaults; `provider = getProvider(providerName)`; require `provider.proxy.base_url` OR `baseUrlOverride` (else `unsupported_provider`).
- If `provider.proxy.base_url` and `endpoint` includes it → strip it from endpoint.
- `headersCleaned` = lowercased keys.
- `multipart/form-data` content-type → build `FormData` from `data` + files.
- Output: `{ endpoint, method (upper, default GET), provider, providerName, providerConfigKey, headers, data, retries (default 0), baseUrlOverride, decompress (=== 'true'|true), params, responseType, retryOn (array|none), forwardHeadersOnRedirect, validateProxyRedirectUrl }`.

## buildProxyURL

- `apiBase = baseUrlOverride || provider.proxy.base_url`.
- If `apiBase` has `${...||...}` → split on `||`; pick index 0 if `connectionConfig.<key>` resolves, else 1.
- strip trailing `/` from base; strip leading `/` from endpoint.
- `interpolateProxyUrlParts` on base and endpoint; join with `/`.
- `interpolateIfNeeded(combined, {connection, connectionConfig, credentials})`.
- `new URL(fullEndpoint)`; apply `params` (string → `?...` appended, error if endpoint already has `?`; object → searchParams.set).
- `provider.proxy.query` → `apiKey` (`${apiKey}` → credentials.apiKey for API_KEY), `connectionConfig.*` interpolation, or static.
- Return `url.toString()`.

## buildProxyHeaders — per credentials.type (default Authorization)

- `BASIC` → `Authorization: Basic base64(username:password)`
- `OAUTH2` / `APP_STORE` / `APP` → `Authorization: Bearer <access_token>`
- `API_KEY` → no default (provider headers carry it)
- `OAUTH2_CC` / `SIGNATURE` / `JWT` → `Authorization: Bearer <token>`
- `TWO_STEP` → `Authorization: Bearer <token>` unless provider headers reference `${accessToken}`
- `TBA` → OAuth1 HMAC-SHA256 signed `OAuth realm="...", ...` (consumer from config_override/connection_config; token_id/token_secret)
- `OAUTH1` → OAuth1 HMAC-SHA1 signed `Authorization` (consumer from integration config oauth_client_id/secret; oauth_token/oauth_token_secret) — `unsupported_auth` if missing
- `CUSTOM` / `undefined` / `BILL` → no default
- default → `unsupported_auth`

Then **provider.proxy.headers** template interpolation (per type replacers):
- `OAUTH2`: `${accessToken}`, `${clientId}`, `${clientSecret}`
- `JWT`/`OAUTH2_CC`/`SIGNATURE`: `${accessToken}`
- `TWO_STEP`: `${accessToken}`, `${credentials}`, plus base replacers
- `connectionConfig.*`: interpolate `connectionConfig`, `credentials`, method, + base replacers
- base replacers: `endpoint`, `host`, `path`, `params` (canonical, buildCanonicalParams), `urlCanonicalParams`, `bodyCanonicalParams` (getRawBody), `contentType`

Then `config.headers` override except `user-agent` (provided headers win for user-agent). Return merged headers.

## Retry (getProxyRetryFromErr)

- non-axios → `{retry:false, reason:'unknown_error'}`.
- network error code (in `networkError` list) → `{retry:true, reason:'network_error'}`.
- `provider.proxy.retry.error_code` array (matchesStatusCode: exact / `Nxx` / `NNN-MMM`) → retry; else default retryable = `>=500 || 429 || 401`.
- `retryOn` header list includes status → retry.
- `provider.proxy.retry.remaining` header == '0' → retry (`provider_remaining`).
- Backoff wait from `retryHeader` (at/after) → provider `retry.at`/`retry.after` headers → `retry.in_body` (regex on body path).
- `at`: epoch seconds (or ms if year>1971, or date string) → wait = (retryAt - now) sec ×1000.
- `after`: seconds ×1000.

## Redirect (beforeRedirect)

- `validateProxyRedirectUrl(absoluteUrl)` → `proxy_redirect_to_denied_host` if denied.
- `forwardHeadersOnRedirect` (default true) → keep original headers (esp. authorization) on redirect.

## Other

- `decompress` (header or `provider.proxy.decompress`) → axios decompress.
- `require_client_certificate` → `client_certificate`/`client_private_key` PEM → https.Agent (cert/key, rejectUnauthorized=false); invalid PEM → `invalid_certificate_or_key_format`.
- multipart `multipart/form-data` → FormData.

## Deferred from this slice (tracked, not blocking)

- Credential refresh / token refresh (`refreshOrTestCredentials`, `connection_refresh_backoff`, `invalid_credentials`) → Phase 5. Proxy uses stored decrypted credentials.
- Plan capping → billing, out of scope.
- TBA / OAUTH1 HMAC signing (complex) → Phase 4b (after common modes).
- `retry.in_body` parsing, multipart file uploads, `base_url_override` denylist config → Phase 4b.
- Activity-log/telemetry (logCtx, OTel span, usage.pubsub) → deferred (observability).
- `getRawBody` feature flag → use `req.body`.

## Phase 4a scope (this slice)

Common path: header validation, integration+connection lookup, URL construction
(base_url override + endpoint + `connectionConfig`/`credentials` interpolation),
header building for **OAUTH2 / API_KEY / BASIC / APP** modes + provider
`proxy.headers` template interpolation (`${accessToken}`, `${apiKey}`,
`${clientId}`, `${clientSecret}`, `connectionConfig.*`), upstream HTTP via
httpx, retries (network + default `>=500||429||401` + `retry-on` header,
exponential backoff), redirect header forwarding, decompress, error
passthrough. Route + e2e tests against a mock upstream.