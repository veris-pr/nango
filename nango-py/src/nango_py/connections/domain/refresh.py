"""OAuth2 credential refresh domain logic.

Mirrors ``shouldRefreshCredentials`` and ``parseRawCredentials`` from
``packages/shared/lib/services/connections/credentials/refresh.ts`` +
``packages/shared/lib/services/connection.service.ts``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

JsonObject = dict[str, Any]

REFRESH_MARGIN_SECONDS = 300  # REFRESH_MARGIN_MS / 1000


def should_refresh(
    credentials: JsonObject,
    *,
    instant_refresh: bool,
    provider_entry: JsonObject,
) -> tuple[bool, str]:
    """Determine if OAUTH2 credentials need a token refresh."""
    if credentials.get("type") != "OAUTH2":
        return False, "not_oauth2"

    buffer_seconds = provider_entry.get("token_expiration_buffer") or REFRESH_MARGIN_SECONDS

    if not instant_refresh:
        expires_at = credentials.get("expires_at")
        if not expires_at:
            return False, "no_expires_at"
        expiry = _parse_date(expires_at)
        if expiry is None:
            return False, "invalid_expires_at"
        if expiry > datetime.now(UTC) + timedelta(seconds=buffer_seconds):
            return False, "fresh"

    if not credentials.get("refresh_token") and (
        provider_entry.get("auth_mode") != "microsoft-admin"
    ):
        return False, "no_refresh_token"

    return True, "expired_oauth2_with_refresh_token"


def parse_raw_credentials(raw: JsonObject, old_refresh_token: str | None) -> JsonObject:
    """Parse an OAuth2 token refresh response into credentials dict.

    Mirrors ``parseRawCredentials`` for OAUTH2 mode.
    """
    access_token = raw.get("access_token")
    if not access_token:
        raise ValueError("incomplete_raw_credentials: missing access_token")

    expires_at: str | None = None
    if raw.get("expires_at"):
        expires_at = str(raw["expires_at"])
    elif raw.get("expires_in"):
        try:
            expires_in = int(raw["expires_in"])
            expires_at = (
                datetime.now(UTC) + timedelta(seconds=expires_in)
            ).isoformat()
        except (ValueError, TypeError):
            pass

    return {
        "type": "OAUTH2",
        "access_token": access_token,
        "refresh_token": raw.get("refresh_token") or old_refresh_token,
        "expires_at": expires_at,
        "raw": raw,
    }


def get_expires_at_from_credentials(credentials: JsonObject) -> datetime | None:
    """Extract expires_at from credentials (for DB column update)."""
    raw_expires = credentials.get("expires_at")
    if not raw_expires:
        return None
    return _parse_date(raw_expires)


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None