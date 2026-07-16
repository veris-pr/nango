# How-to: Fix a parity delta

> **Task:** Diagnose and fix a mismatch between TypeScript and Python
> responses for the same request.

A parity delta is any difference between the TypeScript backend response and
the Python backend response for the same input. Even small differences
(different key casing, missing null fields, different error code) break
customer SDKs.

## Step 1 — Reproduce the delta

Run the parity test that fails:

```bash
cd nango-py
uv run pytest tests/parity/test_integration_fixtures.py -v -k "failing_test_name"
```

Or run both backends and compare manually:

```bash
# TypeScript backend
curl -s http://localhost:3003/integrations/google -H "Authorization: Bearer $SECRET" | jq

# Python backend
curl -s http://localhost:3004/integrations/google -H "Authorization: Bearer $SECRET" | jq
```

## Step 2 — Diff the responses

```bash
diff <(ts_response | jq -S) <(py_response | jq -S)
```

Identify the field(s) that differ. Common delta types:

| Delta type | Example | Fix location |
|------------|---------|--------------|
| Missing field | Python omits `webhook_url` | Transport serialize or domain view |
| Different casing | `connectionId` vs `connection_id` | Pydantic alias or dict key |
| Different null handling | TS sends `null`, Python omits key | Use `NOT_SET` marker |
| Different error code | `not_found` vs `unknown_integration` | Domain error class |
| Different status code | TS 404, Python 400 | Error class `status` field |
| Different error envelope | `{error: {code}}` vs `{error: {message, code, payload}}` | Wrong `ApiError` subclass |

## Step 3 — Read the TypeScript controller

Find the authoritative TypeScript code:

```
packages/server/lib/controllers/<area>/<controller>.ts
```

Read how it constructs the response. Look for:
- Conditional key assignment (`if (x) { body.x = x }`)
- Explicit `null` vs omission
- Response casing (camelCase keys)
- Error envelope shape

## Step 4 — Find the Python code that produces the field

Trace the field back through the layers:

```
Transport route → use case → domain view → serialize
```

The fix is usually in:
- **Transport serialize** — key names, null vs omission
- **Domain view** — the `NOT_SET` marker for omitted keys
- **Error class** — wrong `code` or `status`

## Step 5 — Fix the Python code

### Missing field fix

If TS includes a field that Python omits, add it to the domain view:

```python
@dataclass(frozen=True)
class PublicIntegrationView:
    ...
    webhook_url: str | None | _NotSet = NOT_SET  # omit when not requested
```

### Null vs omission fix

TS distinguishes `null` from missing. Python uses `NOT_SET`:

```python
# If TS sends null → use None
# If TS omits key → use NOT_SET
# In serialize:
if not isinstance(view.webhook_url, _NotSet):
    result["webhook_url"] = view.webhook_url  # includes None as null
```

### Error code fix

Match the exact error code from the TS controller:

```python
class IntegrationNotFound(ApiError):
    status = 404
    code = "unknown_integration"  # exact TS code
    message = "..."
```

### Error envelope fix

Check which envelope the TS uses:
- Direct: `{error: {code, message?}}` → `ApiError`
- NangoError: `{error: {message, code, payload}}` → `NangoApiError`
- Validation: `{error: {code, errors: [...]}}` → `ValidationApiError`

See [error envelope reference](../reference/error-envelopes.md).

## Step 6 — Re-run parity

```bash
uv run pytest tests/parity/ -v -k "failing_test_name"
```

Then run the full suite:

```bash
uv run pytest -q
```

## Step 7 — Document accepted deltas

If a delta is intentionally accepted (e.g., a deprecated field Python
deliberately omits), document it in the test with a comment:

```python
# Accepted delta: Python omits deprecated "syncType" field
# See PythonCoreContractInventory.md §6
```

## Common delta patterns

### Key casing

TS uses camelCase. Python domain uses snake_case. Serialize with aliases:

```python
return {"connectionId": conn.connection_id}  # explicit camelCase
```

### Timestamp format

TS uses ISO 8601 with `Z` suffix. Python datetime isoformat uses `+00:00`:

```python
def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")
```

### Empty array vs null

TS sends `[]` for empty arrays. Python may send `null` or omit:

```python
# Fix: default to empty list, not None
tags: list[str] = field(default_factory=list)
```