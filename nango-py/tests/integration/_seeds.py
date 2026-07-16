"""Shared seed helpers for integration tests against the migrated schema."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.shared.crypto import encrypt_aes_gcm, hash_secret

DEFAULT_KEY = "EnK3hn3VlrXsQ3QI3J9ozbTxgVolLD7XWJXABt0R4i0="
DEFAULT_TEST_KEY = "11111111-1111-4111-8111-111111111111"


async def seed_account(
    session_factory: async_sessionmaker[AsyncSession], name: str = "test-team"
) -> int:
    async with session_factory() as s:
        row = (
            await s.execute(
                text("INSERT INTO _nango_accounts (name) VALUES (:n) RETURNING id"),
                {"n": name},
            )
        ).mappings().one()
        await s.commit()
    return int(row["id"])


async def seed_environment(
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


async def seed_api_secret(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    environment_id: int,
    plaintext: str,
    is_default: bool = True,
    encryption_key: str = DEFAULT_KEY,
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


async def seed_customer_key(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    account_id: int,
    environment_id: int,
    plaintext: str,
    scopes: list[str],
    encryption_key: str = DEFAULT_KEY,
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


async def seed_integration(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    environment_id: int,
    unique_key: str,
    provider: str,
    oauth_client_id: str | None = "client-123",
    oauth_client_secret: str | None = "secret-456",
    oauth_scopes: str | None = "repo,user",
    app_link: str | None = None,
    custom: dict[str, object] | None = None,
    display_name: str | None = "Integration",
    forward_webhooks: bool = True,
    shared_credentials_id: int | None = None,
    deleted: bool = False,
    encryption_key: str = DEFAULT_KEY,
) -> int:
    if encryption_key and oauth_client_secret is not None:
        secret, iv, tag = encrypt_aes_gcm(oauth_client_secret, encryption_key)
    else:
        secret, iv, tag = oauth_client_secret or "", "", ""
    custom_json = json.dumps(custom) if custom is not None else None
    async with session_factory() as s:
        row = (
            await s.execute(
                text(
                    """
                    INSERT INTO _nango_configs
                    (unique_key, provider, environment_id, oauth_client_id,
                     oauth_client_secret, oauth_client_secret_iv, oauth_client_secret_tag,
                     oauth_scopes, app_link, custom, display_name, forward_webhooks,
                     shared_credentials_id, missing_fields, deleted)
                    VALUES
                    (:uk, :prov, :eid, :cid, :csec, :iv, :tag, :scopes, :app, :custom,
                     :dn, :fw, :shared, :missing, :deleted)
                    RETURNING id
                    """
                ),
                {
                    "uk": unique_key,
                    "prov": provider,
                    "eid": environment_id,
                    "cid": oauth_client_id,
                    "csec": secret,
                    "iv": iv,
                    "tag": tag,
                    "scopes": oauth_scopes,
                    "app": app_link,
                    "custom": custom_json,
                    "dn": display_name,
                    "fw": forward_webhooks,
                    "shared": shared_credentials_id,
                    "missing": [],
                    "deleted": deleted,
                },
            )
        ).mappings().one()
        await s.commit()
    return int(row["id"])


async def seed_full_auth(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    scopes: list[str],
    plaintext: str = DEFAULT_TEST_KEY,
) -> tuple[int, str]:
    """Seed account + environment + default api_secret + one customer key."""
    account_id = await seed_account(session_factory)
    env_id, env_uuid = await seed_environment(session_factory, account_id)
    await seed_api_secret(session_factory, environment_id=env_id, plaintext="default-plain")
    await seed_customer_key(
        session_factory,
        account_id=account_id,
        environment_id=env_id,
        plaintext=plaintext,
        scopes=scopes,
    )
    return env_id, env_uuid


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


__all__: list[Any] = [
    "DEFAULT_KEY",
    "DEFAULT_TEST_KEY",
    "iso",
    "seed_account",
    "seed_api_secret",
    "seed_customer_key",
    "seed_environment",
    "seed_full_auth",
    "seed_integration",
]