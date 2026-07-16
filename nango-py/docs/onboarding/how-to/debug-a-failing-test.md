# How-to: Debug a failing test

> **Task:** Diagnose and fix a failing test in the Python port.

Follow the debugging workflow: reproduce, localize, reduce, root-cause, fix,
guard.

## Step 1 — Reproduce

Run the failing test in isolation:

```bash
cd nango-py
uv run pytest tests/integration/test_providers_route.py::test_get_provider_success -v -s
```

The `-s` flag shows print output. The `-v` flag shows full test names.

If it only fails in the full suite, run with `-x` to stop at first failure:

```bash
uv run pytest -x -v -s
```

## Step 2 — Read the error

### Pytest assertion failure

```
E   assert response.status_code == 200
E   assert 404 == 200
```

The response is 404, not 200. Check:
- Is the seed data present? (Did `seed_provider` fixture run?)
- Is the route wired? (Check `server/app.py`)
- Is the path correct? (Check the test URL)

### Mypy type error

```
error: Argument 1 to "execute" has incompatible type "ImmediateRequest";
       expected "ImmediateTaskInput" [arg-type]
```

You're passing the wrong type. Check:
- Are you passing a transport model where a domain model is expected?
- Do you need a conversion function? (e.g., `_to_immediate_input`)

### Ruff lint error

```
F841 Local variable `body` is assigned to but never used
```

Remove the unused variable or prefix with `_`:

```python
await request.body()  # was: body = await request.body()
```

### Import error

```
E   ModuleNotFoundError: No module named 'nango_py.orchestrator'
```

The module path is wrong. Check:
- Does the module exist? (e.g., it's `scheduler` not `orchestrator`)
- Is there an `__init__.py` in the package?
- Is the import in `server/app.py` correct?

### Testcontainer failure

```
E   docker.errors.DockerException: Error while fetching server API version
```

Docker isn't running. Start Docker Desktop.

### Migration failure

```
E   subprocess.CalledProcessError: Command 'node tools/migrate.mjs ...'
```

Check:
- Is Node.js installed and on PATH?
- Is the database URL correct?
- Can the script find the migration files?

## Step 3 — Localize

Add print statements or use `-s` to see what's happening:

```python
async def test_get_provider_success(client, auth_headers):
    response = await client.get("/providers/google", headers=auth_headers)
    print(f"Status: {response.status_code}")
    print(f"Body: {response.text}")
    assert response.status_code == 200
```

Or use a debugger:

```python
import pdb; pdb.set_trace()  # or breakpoint()
```

## Step 4 — Reduce

Isolate the failure:
- Does it fail with a different provider?
- Does it fail without auth headers?
- Does it fail in a unit test (no DB)?
- Does it fail with a minimal seed?

The smallest reproduction is the easiest to fix.

## Step 5 — Root-cause

### The failure is in domain logic

Read the domain dataclass and the use case. Check:
- Are the field names correct?
- Are the types correct?
- Is the invariant being enforced?

### The failure is in infrastructure

Read the SQLAlchemy query. Check:
- Does the SQL match the TypeScript query?
- Are the column names correct?
- Is the search_path correct?
- Are UUIDs handled correctly?

### The failure is in transport

Read the route and serializer. Check:
- Is the path correct?
- Are the query params validated?
- Is the response key casing correct (camelCase)?
- Are null fields handled correctly (None vs NOT_SET)?

### The failure is a parity delta

If the test passes but parity fails, see
[the porting fix-a-parity-delta guide](../porting/how-to/fix-a-parity-delta.md).

## Step 6 — Fix

Make the minimal change that fixes the root cause. Don't add workarounds.

## Step 7 — Guard

Add a test that would have caught the bug:

```python
async def test_get_provider_with_empty_catalog(client, auth_headers):
    """Regression: provider not found should return 404, not 500."""
    response = await client.get("/providers/nonexistent", headers=auth_headers)
    assert response.status_code == 404
```

## Common failure patterns

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| 401 on all requests | Auth gateway not wired | Check `app.state.auth_gateway` in `app.py` |
| 404 on all routes | Router not included | Check `app.include_router()` in `app.py` |
| 500 on DB queries | Wrong search_path | Add `connect_args={'server_settings': {'search_path': 'nango'}}` |
| `None` where `[]` expected | Default factory missing | Use `field(default_factory=list)` |
| Wrong key casing | Serialize not using camelCase | Return `{"connectionId": ...}` not `{"connection_id": ...}` |
| Timestamp format wrong | Not converting `+00:00` to `Z` | Use `_iso()` helper |
| Mypy import-untyped | Package lacks stubs | Add `# type: ignore[import-untyped]` |