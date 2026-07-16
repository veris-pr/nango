"""Seed helpers for connection-related rows: end_users, _nango_connections, _nango_active_logs."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.shared.crypto import encrypt_aes_gcm
from tests.integration._seeds import DEFAULT_KEY


async def seed_end_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    account_id: int,
    environment_id: int,
    end_user_id: str,
    email: str | None = None,
    display_name: str | None = None,
    organization_id: str | None = None,
    organization_display_name: str | None = None,
    tags: dict[str, object] | None = None,
) -> int:
    async with session_factory() as s:
        row = (
            await s.execute(
                text(
                    """
                    INSERT INTO end_users
                    (end_user_id, account_id, environment_id, email, display_name,
                     organization_id, organization_display_name, tags)
                    VALUES (:euid, :aid, :eid, :email, :dn, :oid, :odn, :tags)
                    RETURNING id
                    """
                ),
                {
                    "euid": end_user_id,
                    "aid": account_id,
                    "eid": environment_id,
                    "email": email,
                    "dn": display_name,
                    "oid": organization_id,
                    "odn": organization_display_name,
                    "tags": json.dumps(tags) if tags is not None else None,
                },
            )
        ).mappings().one()
        await s.commit()
    return int(row["id"])


async def seed_connection(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    environment_id: int,
    config_id: int,
    connection_id: str,
    provider_config_key: str,
    credentials: dict[str, object],
    end_user_id: int | None = None,
    tags: dict[str, str] | None = None,
    metadata: dict[str, object] | None = None,
    connection_config: dict[str, object] | None = None,
    last_fetched_at: Any = None,
    deleted: bool = False,
    encryption_key: str = DEFAULT_KEY,
) -> int:
    if encryption_key:
        ct, iv, tag = encrypt_aes_gcm(json.dumps(credentials), encryption_key)
        stored_credentials = json.dumps({"encrypted_credentials": ct})
        credentials_iv = iv
        credentials_tag = tag
    else:
        stored_credentials = json.dumps(credentials)
        credentials_iv = None
        credentials_tag = None

    async with session_factory() as s:
        row = (
            await s.execute(
                text(
                    """
                    INSERT INTO _nango_connections
                    (environment_id, config_id, connection_id, provider_config_key,
                     credentials, credentials_iv, credentials_tag, connection_config,
                     metadata, tags, end_user_id, last_fetched_at, deleted)
                    VALUES (:eid, :cid, :conn, :pck, :creds, :iv, :tag, :cc, :meta,
                     :tags, :euid, :lf, :del)
                    RETURNING id
                    """
                ),
                {
                    "eid": environment_id,
                    "cid": config_id,
                    "conn": connection_id,
                    "pck": provider_config_key,
                    "creds": stored_credentials,
                    "iv": credentials_iv,
                    "tag": credentials_tag,
                    "cc": json.dumps(connection_config) if connection_config is not None else None,
                    "meta": json.dumps(metadata) if metadata is not None else None,
                    "tags": json.dumps(tags or {}),
                    "euid": end_user_id,
                    "lf": last_fetched_at,
                    "del": deleted,
                },
            )
        ).mappings().one()
        await s.commit()
    return int(row["id"])


async def seed_active_log(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    connection_id: int,
    type_value: str,
    log_id: str,
    active: bool = True,
) -> int:
    async with session_factory() as s:
        row = (
            await s.execute(
                text(
                    """
                    INSERT INTO _nango_active_logs
                    (type, action, connection_id, log_id, active)
                    VALUES (:type, 'sync', :cid, :log, :active)
                    RETURNING id
                    """
                ),
                {
                    "type": type_value,
                    "cid": connection_id,
                    "log": log_id,
                    "active": active,
                },
            )
        ).mappings().one()
        await s.commit()
    return int(row["id"])


__all__: list[Any] = ["seed_active_log", "seed_connection", "seed_end_user"]