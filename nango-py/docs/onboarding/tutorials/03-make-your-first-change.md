# Tutorial: Make your first change

> **Goal:** Add a field to an API response, following the DDD layering. By
> the end you'll have made a real change that passes all gates.

We'll add a `provider_display_name` field to the `GET /integrations/:uniqueKey`
response. This touches all four DDD layers and teaches the full workflow.

## The change

The integration read endpoint returns a `PublicIntegrationView`. We want to
add the provider's display name alongside the integration's display name.

## Step 1 — Read the TypeScript controller

Start with the source of truth:

```
packages/server/lib/controllers/integrations/uniqueKey/getIntegration.ts
packages/server/lib/formatters/integration.ts
```

See how the TypeScript builds the response. The `ApiPublicIntegration` type
in `packages/types/lib/integration/api.ts` defines the response shape.

Note: if the TypeScript response already has this field, we're just matching
it. If it doesn't, this is a new feature that needs TypeScript-first design.

For this tutorial, assume TypeScript already returns `provider_display_name`.

## Step 2 — Update the domain view

The domain owns the data shape. Add the field to `PublicIntegrationView`:

```python
# src/nango_py/integrations/domain/integration.py

@dataclass(frozen=True)
class PublicIntegrationView:
    unique_key: str
    provider: str
    display_name: str
    logo: str
    forward_webhooks: bool
    created_at: datetime
    updated_at: datetime
    provider_display_name: str = ""  # ← NEW FIELD
    webhook_url: str | None | _NotSet = NOT_SET
    credentials: CredentialsView | None | _NotSet = NOT_SET
```

Note: frozen dataclasses with defaults must put default fields after
non-default fields.

## Step 3 — Update the use case

The use case builds the view. Add the provider's display name:

```python
# src/nango_py/integrations/application/get_integration.py

def _build_view(
    self,
    integration: Integration,
    provider: Provider,
    request: GetIntegrationRequest,
) -> PublicIntegrationView:
    # ... existing code ...
    return PublicIntegrationView(
        unique_key=integration.unique_key,
        provider=integration.provider,
        display_name=integration.display_name or provider.display_name,
        logo=f"{self._base_public_url}/images/template-logos/{integration.provider}.svg",
        forward_webhooks=integration.forward_webhooks,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
        provider_display_name=provider.display_name,  # ← NEW
        webhook_url=webhook_url,
        credentials=credentials,
    )
```

The use case gets the provider display name from the `Provider` domain object,
which it already has from the catalog lookup.

## Step 4 — Update the serializer

The transport serializer converts the domain view to a JSON dict:

```python
# src/nango_py/integrations/transport/serialize.py

def view_to_dict(view: PublicIntegrationView) -> dict[str, Any]:
    result: dict[str, Any] = {
        "unique_key": view.unique_key,
        "provider": view.provider,
        "display_name": view.display_name,
        "logo": view.logo,
        "forward_webhooks": view.forward_webhooks,
        "created_at": _iso(view.created_at),
        "updated_at": _iso(view.updated_at),
        "provider_display_name": view.provider_display_name,  # ← NEW
    }
    # ... conditional fields ...
    return result
```

## Step 5 — Update the test

Find the existing test for this endpoint:

```bash
cat tests/integration/test_integrations_route.py
```

Add an assertion for the new field:

```python
async def test_get_integration_includes_provider_display_name(
    client, auth_headers, seed_integration
):
    response = await client.get(
        "/integrations/google",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert "provider_display_name" in body
    assert body["provider_display_name"] == "Google"
```

## Step 6 — Run the gates

```bash
cd nango-py

# Lint
uv run ruff check .

# Type check
uv run mypy

# Run the test
uv run pytest tests/integration/test_integrations_route.py -v
```

If all three pass, your change is complete.

## Step 7 — Run the full suite

Make sure your change didn't break anything else:

```bash
uv run pytest -q
```

## What you learned

The DDD layering means every change touches four layers in order:

```
1. Domain       → Add field to the dataclass
2. Application  → Populate the field in the use case
3. Transport    → Serialize the field in the response
4. Test         → Assert the field appears
```

This structure makes changes predictable:
- You always know which layer to modify
- Each layer has one responsibility
- The dependency direction ensures no circular changes
- Tests verify each layer independently

## Why this workflow works

- **Domain first** — You define the data shape before wiring anything
- **Use case second** — You decide how to populate it
- **Transport last** — You decide how to expose it
- **Test always** — You prove it works before declaring done

This is the workflow for every change, from a single field to a new endpoint.