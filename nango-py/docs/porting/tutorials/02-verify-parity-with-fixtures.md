# Tutorial: Verify parity with fixtures

> **Goal:** Prove your Python endpoint produces the same response as the
> TypeScript endpoint for the same input.

Parity is the core of this port. A passing Python test is not enough — the
response must match what the TypeScript backend would produce. This tutorial
shows how to use contract fixtures and the differential harness to prove it.

## Why fixtures matter

The TypeScript backend is the source of truth. If Python produces a different
response shape, different status code, or different error envelope, customer
SDKs break. Fixtures freeze the TypeScript contract so you can verify Python
against it without running both servers simultaneously.

## Step 1 — Find or generate the fixture

Contract fixtures live in `nango-py/tests/contract/`. Each fixture is a JSON
file generated from authoritative TypeScript behavior.

For example, the integration read endpoint has fixtures in:

```
tests/contract/integrations/fixtures/get_by_key/
  success_credentials_include_oauth2.json
  missing_auth.json
  missing_scope.json
  unknown_integration.json
  ...
```

Each fixture captures: the request (method, path, headers, query, body) and
the expected response (status, headers, JSON body).

## Step 2 — Write a contract test

Contract tests consume fixtures and assert Python matches:

```python
# tests/contract/test_fixtures_load.py

@pytest.mark.parametrize("fixture_file", FIXTURE_FILES)
def test_fixture_loads(fixture_file):
    fixture = json.loads(Path(fixture_file).read_text())
    request_spec = fixture["request"]
    expected = fixture["response"]

    # Run the request against the Python app
    response = client.request(
        method=request_spec["method"],
        url=request_spec["path"],
        headers=request_spec.get("headers", {}),
        params=request_spec.get("query"),
    )

    assert response.status_code == expected["status"]
    assert response.json() == expected["body"]
```

## Step 3 — Handle nondeterministic values

Some values change between runs (timestamps, UUIDs). Normalize them:

```python
def normalize(body: dict) -> dict:
    if "created_at" in body:
        body["created_at"] = "<normalized:datetime>"
    if "updated_at" in body:
        body["updated_at"] = "<normalized:datetime>"
    return body
```

Only normalize documented nondeterministic values. Do not normalize away real
differences — those are parity bugs.

## Step 4 — Run the parity harness

The parity test suite runs the same scenarios against both TypeScript and
Python backends simultaneously:

```bash
# Start both backends
# TypeScript: cd packages/server && npm run dev
# Python: cd nango-py && uv run python -m nango_py.run

cd nango-py
uv run pytest tests/parity/ -v
```

Parity tests compare the live responses from both servers:

```python
# tests/parity/test_integration_fixtures.py

async def test_integration_read_parity(ts_client, py_client, auth_headers):
    ts_response = await ts_client.get("/integrations/google", headers=auth_headers)
    py_response = await py_client.get("/integrations/google", headers=auth_headers)

    assert ts_response.status_code == py_response.status_code
    assert ts_response.json() == py_response.json()
```

## Step 5 — Diagnose a parity delta

If responses don't match, follow the [fix a parity delta](../how-to/fix-a-parity-delta.md)
guide. The workflow:

1. Compare the two responses field by field
2. Read the TypeScript controller to find the source of the differing field
3. Find the Python code that should produce it
4. Fix the Python code
5. Re-run parity

## What you learned

- Fixtures freeze TypeScript contracts
- Contract tests consume fixtures offline
- Parity tests run both backends live and compare
- Nondeterministic values are normalized, real differences are bugs
- Every ported endpoint needs both contract and parity tests

Next: [add a new auth flow](./03-add-a-new-auth-flow.md).