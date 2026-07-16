# Reference: Error envelopes

> The three error envelope shapes the TypeScript backend uses and their
> Python counterparts.

The TypeScript backend uses three distinct error response shapes. Python must
match the exact shape for each error type, or customer SDKs will fail to parse
them.

## Shape 1 — Direct error envelope

```json
{"error": {"code": "not_found", "message": "Integration not found"}}
```

Used by most error handlers that send `res.status().send({error: {code, message}})`.

### Python: `ApiError`

```python
from nango_py.shared.errors import ApiError

class IntegrationNotFound(ApiError):
    status = 404
    code = "unknown_integration"
    message = "Integration not found"
```

Fields:
- `status` — HTTP status code
- `code` — stable error code string (matches TypeScript)
- `message` — optional human-readable message (omitted from envelope if empty)

The composition root catches `ApiError` and serializes it:

```python
@app.exception_handler(ApiError)
async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(exc.to_envelope(), status_code=exc.status)
```

## Shape 2 — NangoError envelope

```json
{"error": {"message": "Missing Authorization header", "code": "missing_auth_header", "payload": {}}}
```

Used by errors raised through the TypeScript `NangoError` path (auth errors).
Always includes `payload` (defaults to `{}`) and `message`.

### Python: `NangoApiError`

```python
from nango_py.shared.errors import NangoApiError

class MissingAuthHeader(NangoApiError):
    status = 401
    code = "missing_auth_header"
    message = "Missing Authorization header"
    payload = {}  # default
```

The `to_envelope()` method produces the three-key shape:

```python
def to_envelope(self) -> dict[str, Any]:
    return {"error": {"message": self.message, "code": self.code, "payload": self.payload}}
```

## Shape 3 — Validation error envelope

```json
{"error": {"code": "invalid_query_params", "errors": [{"code": "invalid_enum_value", "message": "...", "path": ["include"]}]}}
```

Used by Zod validation failures (`zodErrorToHTTP`). Includes a list of field
issues, not a single message.

### Python: `ValidationApiError`

```python
from nango_py.shared.errors import ValidationApiError

raise ValidationApiError(
    "invalid_query_params",
    [{"code": "invalid_enum_value", "message": "Expected 'webhook' | 'credentials'", "path": ["include"]}],
)
```

Fields:
- `status` — always 400
- `code` — validation error code (e.g., `invalid_body`, `invalid_query_params`, `invalid_uri_params`, `invalid_headers`)
- `errors` — list of `{code, message, path}` issue objects

## Common error codes

| Code | Status | Envelope | When |
|------|--------|----------|------|
| `missing_auth_header` | 401 | NangoError | No Authorization header |
| `malformed_auth_header` | 401 | NangoError | Bad Bearer format |
| `invalid_secret_key_format` | 401 | NangoError | Token not UUID v4 |
| `unknown_account` | 401 | NangoError | No matching account |
| `forbidden` | 403 | Direct | Missing scope |
| `unknown_integration` | 404 | Direct | Integration not found |
| `unknown_provider` | 404 | Direct | Provider not in catalog |
| `unknown_provider_config` | 400 | Direct | Provider config not found |
| `not_found` | 404 | Direct | Generic not found |
| `invalid_body` | 400 | Validation | Body parse failure |
| `invalid_query_params` | 400 | Validation | Query validation failure |
| `invalid_uri_params` | 400 | Validation | Path param validation |
| `invalid_headers` | 400 | Validation | Header validation |

## Choosing the right envelope

1. Is it a Zod-style validation failure with field paths? → `ValidationApiError`
2. Is it an auth error (missing/malformed/invalid token)? → `NangoApiError`
3. Everything else? → `ApiError` (direct)

## Scope wildcard semantics

The `Scopes` class mirrors `hasScope` in `packages/server/lib/middleware/scope.middleware.ts`:

- Exact match wins: `"environment:syncs:execute"` matches `"environment:syncs:execute"`
- Wildcard prefix: `"environment:*"` matches any scope starting with `"environment:"`
- `has_any()` checks if any of the required scopes match

```python
READ_SCOPE = "environment:integrations:read"
READ_CREDENTIALS_SCOPE = "environment:integrations:read_credentials"
REQUIRED_SCOPES = (READ_SCOPE, READ_CREDENTIALS_SCOPE)

if not scopes.has_any(REQUIRED_SCOPES):
    raise Forbidden(REQUIRED_SCOPES)
```