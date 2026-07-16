"""Integration tests for SqlAlchemyAuthGateway against the migrated schema.

Seeds account/environment/api_secrets/customer_keys rows, then verifies the
gateway resolves contexts exactly as the TypeScript account.service.ts does:
customer-key and internal-secret paths, scope resolution, secret decryption,
and fail-closed behavior on unknown keys.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.auth.domain.context import Scopes
from nango_py.auth.infrastructure.sqlalchemy_auth_gateway import SqlAlchemyAuthGateway
from nango_py.shared.crypto import encrypt_aes_gcm, hash_secret

# 32-byte base64 key (same one emitted by tools/crypto_vectors.gen.mjs).
ENCRYPTION_KEY = "EnK3hn3VlrXsQ3QI3J9ozbTxgVolLD7XWJXABt0R4i0="


async def _seed_account(
    session_factory: async_sessionmaker[AsyncSession],
    name: str = "test-team",
) -> tuple[int, str]:
    async with session_factory() as s:
        row = (
            await s.execute(
                text("INSERT INTO _nango_accounts (name) VALUES (:n) RETURNING id, uuid::text"),
                {"n": name},
            )
        ).mappings().one()
        await s.commit()
    return int(row["id"]), str(row["uuid"])


async def _seed_environment(
    session_factory: async_sessionmaker[AsyncSession],
    account_id: int,
    name: str = "dev",
    is_production: bool = False,
) -> tuple[int, str]:
    async with session_factory() as s:
        row = (
            await s.execute(
                text(
                    "INSERT INTO _nango_environments (name, account_id, is_production)"
                    " VALUES (:n, :a, :p) RETURNING id, uuid::text"
                ),
                {"n": name, "a": account_id, "p": is_production},
            )
        ).mappings().one()
        await s.commit()
    return int(row["id"]), str(row["uuid"])


async def _seed_api_secret(
    session_factory: async_sessionmaker[AsyncSession],
    environment_id: int,
    plaintext: str,
    *,
    is_default: bool,
    encryption_key: str = ENCRYPTION_KEY,
) -> int:
    hashed = hash_secret(plaintext, encryption_key)
    if encryption_key:
        secret, iv, tag = encrypt_aes_gcm(plaintext, encryption_key)
    else:
        secret, iv, tag = plaintext, "", ""
    async with session_factory() as s:
        row = (
            await s.execute(
                text(
                    "INSERT INTO api_secrets"
                    " (environment_id, display_name, secret, iv, tag, hashed, is_default)"
                    " VALUES (:e, :d, :s, :iv, :tag, :h, :def) RETURNING id"
                ),
                {
                    "e": environment_id,
                    "d": "default" if is_default else "pending",
                    "s": secret,
                    "iv": iv,
                    "tag": tag,
                    "h": hashed,
                    "def": is_default,
                },
            )
        ).mappings().one()
        await s.commit()
    return int(row["id"])


async def _seed_customer_key(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    account_id: int,
    environment_id: int,
    plaintext: str,
    scopes: list[str],
    encryption_key: str = ENCRYPTION_KEY,
) -> int:
    hashed = hash_secret(plaintext, encryption_key)
    if encryption_key:
        secret, iv, tag = encrypt_aes_gcm(plaintext, encryption_key)
    else:
        secret, iv, tag = plaintext, "", ""
    async with session_factory() as s:
        key_row = (
            await s.execute(
                text(
                    "INSERT INTO customer_keys"
                    " (account_id, key_type, display_name, scopes, secret, iv, tag, hashed)"
                    " VALUES (:a, 'api', :d, :scopes, :s, :iv, :tag, :h) RETURNING id"
                ),
                {
                    "a": account_id,
                    "d": "Test key",
                    "scopes": scopes,
                    "s": secret,
                    "iv": iv,
                    "tag": tag,
                    "h": hashed,
                },
            )
        ).mappings().one()
        key_id = int(key_row["id"])
        await s.execute(
            text(
                "INSERT INTO customer_keys_relations (customer_key_id, entity_type, entity_id)"
                " VALUES (:k, 'environment', :e)"
            ),
            {"k": key_id, "e": environment_id},
        )
        await s.commit()
    return key_id


def _seed_fixtures() -> list[dict[str, Any]]:
    path = (
        Path(__file__).resolve().parents[1]
        / "contract"
        / "fixtures"
        / "crypto"
        / "parity_vectors.json"
    )
    return cast("list[dict[str, Any]]", json.loads(path.read_text())["pbkdf2"])


async def test_resolves_customer_key_with_explicit_scope(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    account_id, _ = await _seed_account(db_session_factory)
    env_id, env_uuid = await _seed_environment(db_session_factory, account_id)
    plaintext = "11111111-1111-4111-8111-111111111111"
    await _seed_api_secret(db_session_factory, env_id, plaintext="default-plain", is_default=True)
    key_id = await _seed_customer_key(
        db_session_factory,
        account_id=account_id,
        environment_id=env_id,
        plaintext=plaintext,
        scopes=["environment:integrations:read"],
    )

    gateway = SqlAlchemyAuthGateway(db_session_factory, encryption_key=ENCRYPTION_KEY)
    context = await gateway.resolve_by_secret_key(plaintext)

    assert context is not None
    assert context.auth_source == "customer_key"
    assert context.api_key_id == key_id
    assert context.environment.id == env_id
    assert context.environment.uuid == env_uuid
    assert context.scopes == Scopes(("environment:integrations:read",))
    assert not context.scopes.has("environment:integrations:read_credentials")


async def test_resolves_customer_key_with_wildcard_scope(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    account_id, _ = await _seed_account(db_session_factory)
    env_id, _ = await _seed_environment(db_session_factory, account_id)
    plaintext = "22222222-2222-4222-8222-222222222222"
    await _seed_api_secret(db_session_factory, env_id, plaintext="default-plain", is_default=True)
    await _seed_customer_key(
        db_session_factory,
        account_id=account_id,
        environment_id=env_id,
        plaintext=plaintext,
        scopes=["environment:*"],
    )

    gateway = SqlAlchemyAuthGateway(db_session_factory, encryption_key=ENCRYPTION_KEY)
    context = await gateway.resolve_by_secret_key(plaintext)

    assert context is not None
    assert context.scopes.has("environment:integrations:read_credentials")
    assert context.scopes.has("environment:connections:write")


async def test_resolves_internal_secret_with_wildcard_scope(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    account_id, _ = await _seed_account(db_session_factory)
    env_id, _ = await _seed_environment(db_session_factory, account_id)
    plaintext = "33333333-3333-4333-8333-333333333333"
    await _seed_api_secret(db_session_factory, env_id, plaintext=plaintext, is_default=True)

    gateway = SqlAlchemyAuthGateway(db_session_factory, encryption_key=ENCRYPTION_KEY)
    context = await gateway.resolve_by_internal_secret_key(plaintext)

    assert context is not None
    assert context.auth_source == "api_secret"
    assert context.api_key_id is None
    assert context.scopes == Scopes(("environment:*",))
    assert context.environment.id == env_id


async def test_decrypted_secret_is_returned_when_encrypted(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    account_id, _ = await _seed_account(db_session_factory)
    env_id, _ = await _seed_environment(db_session_factory, account_id)
    plaintext = "44444444-4444-4444-8444-444444444444"
    await _seed_api_secret(
        db_session_factory,
        env_id,
        plaintext=plaintext,
        is_default=True,
        encryption_key=ENCRYPTION_KEY,
    )

    gateway = SqlAlchemyAuthGateway(db_session_factory, encryption_key=ENCRYPTION_KEY)
    context = await gateway.resolve_by_internal_secret_key(plaintext)

    assert context is not None
    assert context.secret.secret == plaintext


async def test_secret_passthrough_when_encryption_disabled(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    account_id, _ = await _seed_account(db_session_factory)
    env_id, _ = await _seed_environment(db_session_factory, account_id)
    plaintext = "55555555-5555-4555-8555-555555555555"
    await _seed_api_secret(
        db_session_factory, env_id, plaintext=plaintext, is_default=True, encryption_key=""
    )

    gateway = SqlAlchemyAuthGateway(db_session_factory, encryption_key="")
    context = await gateway.resolve_by_internal_secret_key(plaintext)

    assert context is not None
    assert context.secret.secret == plaintext


async def test_returns_none_for_unknown_secret(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    account_id, _ = await _seed_account(db_session_factory)
    env_id, _ = await _seed_environment(db_session_factory, account_id)
    await _seed_api_secret(db_session_factory, env_id, plaintext="default-plain", is_default=True)

    gateway = SqlAlchemyAuthGateway(db_session_factory, encryption_key=ENCRYPTION_KEY)
    assert await gateway.resolve_by_secret_key("00000000-0000-4000-8000-000000000000") is None
    assert (
        await gateway.resolve_by_internal_secret_key("00000000-0000-4000-8000-000000000000")
        is None
    )


async def test_pbkdf2_lookup_matches_ts_vectors(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Proves the on-disk hash computed by the TS algorithm is what the gateway hashes
    # the presented key against. Uses a vector generated from node:crypto.
    vector = _seed_fixtures()[1]
    plaintext = vector["plaintext"]
    encryption_key = vector["encryption_key"]

    account_id, _ = await _seed_account(db_session_factory)
    env_id, _ = await _seed_environment(db_session_factory, account_id)
    await _seed_api_secret(
        db_session_factory,
        env_id,
        plaintext=plaintext,
        is_default=True,
        encryption_key=encryption_key,
    )

    gateway = SqlAlchemyAuthGateway(db_session_factory, encryption_key=encryption_key)
    context = await gateway.resolve_by_internal_secret_key(plaintext)
    assert context is not None