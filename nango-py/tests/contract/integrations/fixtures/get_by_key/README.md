# Contract fixtures: GET /integrations/:uniqueKey

Frozen from authoritative TypeScript sources listed in `../get_by_key.md`.

## Placeholder normalization

Fixtures use `{{placeholder}}` tokens for environment-specific values. The differential harness substitutes these before comparing TS vs Python responses:

| Placeholder | Meaning |
|---|---|
| `{{secret_key}}` | UUID v4 seeded into `customer_keys` / `api_secrets` and hashed with `NANGO_ENCRYPTION_KEY` |
| `{{account_uuid}}` | Seeded `_nango_accounts.uuid` |
| `{{environment_uuid}}` | Seeded `_nango_environments.uuid` |
| `{{created_at}}` / `{{updated_at}}` | ISO 8601 UTC timestamps set by seed |
| `{{base_public_url}}` | `NANGO_PUBLIC_SERVER_URL` or `NANGO_SERVER_URL` or `http://localhost:3003` |
| `{{webhook_receive_url}}` | Global webhook receive URL |

## Scenarios

| File | Status | Asserts |
|---|---|---|
| `success_no_include.json` | 200 | base public DTO, no webhook_url/credentials keys |
| `success_webhook_include.json` | 200 | webhook_url populated when provider has webhook_routing_script |
| `success_credentials_include_oauth2.json` | 200 | OAUTH2 credentials with read_credentials scope |
| `success_credentials_include_app.json` | 200 | APP credentials map (app_id, private_key, app_link) |
| `credentials_excluded_no_scope.json` | 200 | credentials requested but read scope only → credentials key omitted |
| `credentials_empty_shared.json` | 200 | shared_credentials_id set → client_id/client_secret empty |
| `wildcard_scope.json` | 200 | `environment:*` grants read_credentials |
| `missing_scope.json` | 403 | authenticated but no matching scope |
| `unknown_integration.json` | 404 | integration row missing |
| `unknown_provider.json` | 404 | provider not in providers.yaml |
| `missing_auth.json` | 401 | no Authorization header |
| `malformed_auth.json` | 401 | Bearer split empty |
| `invalid_secret_key_format.json` | 401 | token not UUID v4 |
| `unknown_account.json` | 401 | valid UUID, no matching key |
| `invalid_query_params.json` | 400 | bad include enum value |
| `invalid_uri_params.json` | 400 | bad uniqueKey chars |

Out of scope for this slice: `plan_not_found` (billing), `invalid_permissions` guard (unreachable on this route — `apiAuth` only, `authType` is always `secretKey`).