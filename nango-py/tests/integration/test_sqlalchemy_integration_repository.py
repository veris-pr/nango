"""Integration tests for SqlAlchemyIntegrationRepository against the migrated schema."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.integrations.infrastructure.sqlalchemy_integration_repository import (
    SqlAlchemyIntegrationRepository,
)
from nango_py.shared.crypto import encrypt_aes_gcm

ENCRYPTION_KEY = "EnK3hn3VlrXsQ3QI3J9ozbTxgVolLD7XWJXABt0R4i0="


async def _seed_environment(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[int, int]:
    async with session_factory() as s:
        account = (
            await s.execute(
                text("INSERT INTO _nango_accounts (name) VALUES ('t') RETURNING id")
            )
        ).mappings().one()
        env = (
            await s.execute(
                text(
                    "INSERT INTO _nango_environments (name, account_id, is_production)"
                    " VALUES ('dev', :a, false) RETURNING id"
                ),
                {"a": account["id"]},
            )
        ).mappings().one()
        await s.commit()
    return int(account["id"]), int(env["id"])


async def _seed_integration(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    environment_id: int,
    unique_key: str = "github",
    provider: str = "github",
    oauth_client_id: str = "client-123",
    oauth_client_secret: str = "secret-456",
    oauth_scopes: str = "repo,user",
    app_link: str | None = None,
    custom: dict[str, object] | None = None,
    display_name: str | None = "GitHub",
    forward_webhooks: bool = True,
    shared_credentials_id: int | None = None,
    deleted: bool = False,
    encryption_key: str = ENCRYPTION_KEY,
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


async def test_resolves_integration_with_decrypted_oauth_secret(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, env_id = await _seed_environment(db_session_factory)
    await _seed_integration(
        db_session_factory, environment_id=env_id, oauth_client_secret="secret-456"
    )

    repo = SqlAlchemyIntegrationRepository(db_session_factory, encryption_key=ENCRYPTION_KEY)
    integration = await repo.get_by_unique_key(environment_id=env_id, unique_key="github")

    assert integration is not None
    assert integration.unique_key == "github"
    assert integration.provider == "github"
    assert integration.oauth_client_id == "client-123"
    assert integration.oauth_client_secret == "secret-456"
    assert integration.oauth_scopes == "repo,user"
    assert integration.display_name == "GitHub"
    assert integration.forward_webhooks is True
    assert isinstance(integration.created_at, datetime)


async def test_resolves_custom_encrypted_to_dict(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, env_id = await _seed_environment(db_session_factory)
    plain_custom: dict[str, object] = {"webhookSecret": "wh-secret-abc"}
    encrypted_ct, iv, tag = encrypt_aes_gcm(json.dumps(plain_custom), ENCRYPTION_KEY)
    encrypted_custom: dict[str, object] = {
        "encryptedValue": encrypted_ct,
        "iv": iv,
        "authTag": tag,
    }
    await _seed_integration(
        db_session_factory, environment_id=env_id, custom=encrypted_custom
    )

    repo = SqlAlchemyIntegrationRepository(db_session_factory, encryption_key=ENCRYPTION_KEY)
    integration = await repo.get_by_unique_key(environment_id=env_id, unique_key="github")

    assert integration is not None
    assert integration.custom == plain_custom


async def test_secret_passthrough_when_encryption_disabled(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, env_id = await _seed_environment(db_session_factory)
    await _seed_integration(
        db_session_factory,
        environment_id=env_id,
        oauth_client_secret="plain-secret",
        encryption_key="",
    )

    repo = SqlAlchemyIntegrationRepository(db_session_factory, encryption_key="")
    integration = await repo.get_by_unique_key(environment_id=env_id, unique_key="github")

    assert integration is not None
    assert integration.oauth_client_secret == "plain-secret"


async def test_returns_none_for_unknown_key(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, env_id = await _seed_environment(db_session_factory)
    repo = SqlAlchemyIntegrationRepository(db_session_factory, encryption_key=ENCRYPTION_KEY)
    assert await repo.get_by_unique_key(environment_id=env_id, unique_key="ghost") is None


async def test_returns_none_for_wrong_environment(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, env_id = await _seed_environment(db_session_factory)
    await _seed_integration(db_session_factory, environment_id=env_id, unique_key="github")

    repo = SqlAlchemyIntegrationRepository(db_session_factory, encryption_key=ENCRYPTION_KEY)
    assert await repo.get_by_unique_key(environment_id=env_id + 999, unique_key="github") is None


async def test_excludes_deleted_rows(
    clean_db: Any,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, env_id = await _seed_environment(db_session_factory)
    await _seed_integration(db_session_factory, environment_id=env_id, deleted=True)

    repo = SqlAlchemyIntegrationRepository(db_session_factory, encryption_key=ENCRYPTION_KEY)
    assert await repo.get_by_unique_key(environment_id=env_id, unique_key="github") is None