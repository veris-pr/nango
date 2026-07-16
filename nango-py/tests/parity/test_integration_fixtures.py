"""Parity harness: live Python server vs frozen TS contract fixtures.

This is the first step toward dual-backend parity testing. The contract
fixtures (tests/contract/) were frozen from authoritative TypeScript source
code during Phase 1-3 contract study. This harness:

1. Starts a testcontainer Postgres + Knex migrations
2. Seeds the data described in each fixture's ``seed`` block
3. Starts the Python server via ASGI
4. Runs the fixture's request against the Python server
5. Compares status code + response body against the fixture's expected response
6. Normalizes placeholder tokens ({{secret_key}}, {{created_at}}, etc.)

When the TS server is available (Docker migration fix pending), this harness
extends to send the same request to the TS server and compare both.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.server.app import create_app
from tests.integration._seeds import (
    DEFAULT_KEY,
    DEFAULT_TEST_KEY,
    seed_account,
    seed_api_secret,
    seed_customer_key,
    seed_environment,
    seed_integration,
)

FIXTURE_DIR = (
    Path(__file__).resolve().parents[1]
    / "contract" / "integrations" / "fixtures" / "get_by_key"
)

# Placeholder normalization: replace {{tokens}} with concrete values
_PLACEHOLDER_MAP: dict[str, str] = {
    "{{secret_key}}": DEFAULT_TEST_KEY,
    "{{base_public_url}}": "https://public.test",
    "{{webhook_receive_url}}": "https://webhook.test",
}


def _normalize_request(body: Any) -> Any:
    """Replace placeholder tokens for request building (no UUID/timestamp normalization)."""
    if isinstance(body, str):
        for placeholder, value in _PLACEHOLDER_MAP.items():
            body = body.replace(placeholder, value)
        return body
    if isinstance(body, dict):
        return {k: _normalize_request(v) for k, v in body.items()}
    if isinstance(body, list):
        return [_normalize_request(v) for v in body]
    return body


def _normalize_response(body: Any) -> Any:
    """Normalize response for comparison: placeholders + timestamps + UUIDs."""
    if isinstance(body, str):
        for placeholder, value in _PLACEHOLDER_MAP.items():
            body = body.replace(placeholder, value)
        for ts_ph in ("{{created_at}}", "{{updated_at}}", "{{last_fetched_at}}",
                       "{{created_at_2}}", "{{environment_uuid}}", "{{account_uuid}}"):
            body = body.replace(ts_ph, "{{timestamp_or_id}}")
        body = re.sub(
            r"\d{4}-\d{2}-\d{2}T[\d:.+-]+Z?", "{{timestamp_or_id}}", body
        )
        body = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{{timestamp_or_id}}", body, flags=re.IGNORECASE
        )
        return body
    if isinstance(body, dict):
        return {k: _normalize_response(v) for k, v in body.items()}
    if isinstance(body, list):
        return [_normalize_response(v) for v in body]
    return body


def _load_fixtures() -> list[tuple[str, dict[str, Any]]]:
    return [(p.stem, json.loads(p.read_text())) for p in sorted(FIXTURE_DIR.glob("*.json"))]


@pytest.fixture
async def parity_app_and_factory(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> tuple[Any, async_sessionmaker[AsyncSession]]:
    app = create_app(
        session_factory=db_session_factory,
        encryption_key=DEFAULT_KEY,
        base_public_url="https://public.test",
        webhook_receive_url="https://webhook.test",
    )
    return app, db_session_factory


async def _seed_from_fixture(
    factory: async_sessionmaker[AsyncSession],
    fixture: dict[str, Any],
) -> int:
    """Seed the DB based on the fixture's ``seed`` block."""
    seed = fixture.get("seed")
    if seed is None:
        return 0

    account_id = await seed_account(factory, name="parity-test")
    env_id, _ = await seed_environment(factory, account_id, name="dev")

    if seed.get("customer_key"):
        ck = seed["customer_key"]
        await seed_api_secret(factory, environment_id=env_id, plaintext="default-plain")
        await seed_customer_key(
            factory,
            account_id=account_id,
            environment_id=env_id,
            plaintext=DEFAULT_TEST_KEY,
            scopes=ck.get("scopes", ["environment:integrations:read"]),
        )

    if seed.get("integration"):
        integ = seed["integration"]
        await seed_integration(
            factory,
            environment_id=env_id,
            unique_key=integ.get("unique_key", "github"),
            provider=integ.get("provider", "github"),
            oauth_client_id=integ.get("oauth_client_id", "client-123"),
            oauth_client_secret=integ.get("oauth_client_secret", "secret-456"),
            oauth_scopes=integ.get("oauth_scopes", "repo,user"),
            display_name=integ.get("display_name", "GitHub"),
            custom=integ.get("custom"),
            shared_credentials_id=integ.get("shared_credentials_id"),
            app_link=integ.get("app_link"),
        )

    return env_id


_FIXTURES = _load_fixtures()


@pytest.mark.parametrize(
    "fixture_name,fixture",
    _FIXTURES,
    ids=[f[0] for f in _FIXTURES],
)
async def test_parity_fixture(
    parity_app_and_factory: tuple[Any, async_sessionmaker[AsyncSession]],
    fixture_name: str,
    fixture: dict[str, Any],
) -> None:
    """Run a contract fixture against the Python server and compare."""
    app, factory = parity_app_and_factory

    # Seed the DB
    await _seed_from_fixture(factory, fixture)

    # Build the request
    req = fixture["request"]
    method = req["method"]
    path = _normalize_request(req["path"])
    headers = {k: _normalize_request(v) for k, v in req.get("headers", {}).items()}
    query = req.get("query", {})

    # Send the request
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(
            method,
            path,
            headers=headers,
            params=query or None,
        )

    # Compare status
    expected_status = fixture["response"]["status"]
    assert response.status_code == expected_status, (
        f"{fixture_name}: status {response.status_code} != {expected_status}"
    )

    # Compare body (normalized)
    if expected_status == 200 and fixture["response"]["body"]:
        actual_body = _normalize_response(response.json())
        expected_body = _normalize_response(fixture["response"]["body"])
        assert actual_body == expected_body, (
            f"{fixture_name}: body mismatch\n"
            f"  expected: {json.dumps(expected_body, indent=2)}\n"
            f"  actual:   {json.dumps(actual_body, indent=2)}"
        )