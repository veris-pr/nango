# How-to: Add a new provider

> **Task:** Add a new provider to the Nango provider catalog.

The provider catalog is `packages/providers/providers.yaml` — a single YAML
file with 785+ provider definitions. The Python `YamlProviderCatalog` loads
this file and resolves aliases at startup.

## When to add a provider

- A customer requests a new integration target
- The provider has an API with OAuth or API key auth
- The TypeScript catalog already has it (or you're adding it there first)

## Step 1 — Read the TypeScript catalog

The catalog is the **same file** for both backends. Open it:

```bash
cat packages/providers/providers.yaml | head -100
```

See the structure of an existing provider:

```yaml
google:
  display_name: Google
  docs: https://developers.google.com/identity/protocols/oauth2
  auth_mode: OAUTH2
  authorization_url: https://accounts.google.com/o/oauth2/v2/auth
  token_url: https://oauth2.googleapis.com/token
  scope_separator: ' '
  default_scopes:
    - https://www.googleapis.com/auth/userinfo.email
  proxy:
    base_url: https://www.googleapis.com
  logo: google.svg
```

## Step 2 — Understand the fields

| Field | Required | Purpose |
|-------|----------|---------|
| `display_name` | ✅ | Human-readable name |
| `docs` | ✅ | Documentation URL |
| `auth_mode` | ✅ | One of: OAUTH2, OAUTH1, API_KEY, BASIC, APP, APP_STORE, TBA, TWO_STEP, JWT, BILL, SIGNATURE, NONE, OAUTH2_CC |
| `authorization_url` | OAuth only | OAuth2 authorize endpoint |
| `token_url` | OAuth only | OAuth2 token exchange endpoint |
| `scope_separator` | OAuth | Separator for scopes (space, comma, etc.) |
| `default_scopes` | OAuth | Default scopes to request |
| `proxy.base_url` | Proxy | Base URL for proxy requests |
| `logo` | ✅ | Logo file name (in `images/template-logos/`) |
| `aliases` | Optional | List of alias names that resolve to this provider |

## Step 3 — Add the provider to the YAML

Add the new provider at the end of `packages/providers/providers.yaml`:

```yaml
myprovider:
  display_name: My Provider
  docs: https://docs.myprovider.com/api
  auth_mode: OAUTH2
  authorization_url: https://auth.myprovider.com/authorize
  token_url: https://auth.myprovider.com/token
  scope_separator: ' '
  default_scopes:
    - read
    - write
  proxy:
    base_url: https://api.myprovider.com/v1
  logo: myprovider.svg
```

**Important:** The TypeScript catalog is the source of truth. If you're adding
a new provider, add it to `packages/providers/providers.yaml` — not to a
Python-specific file. Both backends share this file.

## Step 4 — Add the logo

Place the logo SVG in the appropriate location:

```bash
# The logo path is relative to the base URL
# e.g., {base_public_url}/images/template-logos/myprovider.svg
```

## Step 5 — Verify with Python

The `YamlProviderCatalog` loads the YAML at startup and resolves aliases.
Test that the new provider loads:

```bash
cd nango-py
uv run python -c "
from nango_py.integrations.infrastructure.provider_catalog import YamlProviderCatalog
catalog = YamlProviderCatalog.from_path('../packages/providers/providers.yaml')
entry = catalog.entry('myprovider')
print(entry)
provider = catalog.get('myprovider')
print(f'Display name: {provider.display_name}')
print(f'Auth mode: {provider.auth_mode}')
"
```

## Step 6 — Test the provider endpoints

```bash
# List providers (should include the new one)
uv run pytest tests/integration/test_providers_route.py -v -k "list"

# Get the specific provider
curl http://localhost:3004/providers/myprovider \
  -H "Authorization: Bearer $SECRET"
```

## Step 7 — Test the integration read

Create an integration using the new provider, then test:

```bash
curl http://localhost:3004/integrations/my-integration \
  -H "Authorization: Bearer $SECRET" | jq .data.provider
# → "myprovider"
```

## Auth mode reference

| Auth mode | Credential type | Auth flow route |
|-----------|----------------|-----------------|
| `OAUTH2` | `{type: "OAUTH2", access_token, refresh_token}` | `GET /oauth/connect/:pck` + `GET /oauth/callback/:pck` |
| `API_KEY` | `{type: "API_KEY", apiKey}` | `POST /api-auth/api-key/:pck` |
| `BASIC` | `{type: "BASIC", username, password}` | `POST /api-auth/basic/:pck` |
| `OAUTH2_CC` | `{type: "OAUTH2_CC", ...}` | `POST /oauth2/auth/:pck` |
| `TBA` | `{type: "TBA", ...}` | `POST /auth/tba/:pck` |
| `TWO_STEP` | `{type: "TWO_STEP", ...}` | `POST /auth/two-step/:pck` |
| `JWT` | `{type: "JWT", ...}` | `POST /auth/jwt/:pck` |
| `NONE` | `{type: "NONE"}` | `POST /auth/unauthenticated/:pck` |

## Checklist

- [ ] Added to `packages/providers/providers.yaml`
- [ ] All required fields present
- [ ] Logo SVG added
- [ ] `YamlProviderCatalog.from_path()` loads it
- [ ] `GET /providers` includes it
- [ ] `GET /providers/myprovider` returns it
- [ ] Integration read works with the new provider
- [ ] Tests pass