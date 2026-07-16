"""Read-side credential transforms.

Only the refresh_token strip is modeled here. Actual token refresh (OAuth
refresh, github-app JWT, ``invalid_credentials`` errors) is deferred to the
auth-flows phase; the read path returns stored credentials.
"""

from __future__ import annotations

from typing import Any

JsonObject = dict[str, Any]


def strip_refresh_token(credentials: JsonObject, *, return_refresh_token: bool) -> JsonObject:
    """Mirror the TypeScript single-GET refresh_token stripping.

    For ``OAUTH2`` credentials when ``return_refresh_token`` is false, remove
    ``refresh_token`` from the credentials and from ``credentials.raw``. Returns
    a new dict; the input is not mutated.
    """
    if return_refresh_token:
        return credentials
    if credentials.get("type") != "OAUTH2":
        return credentials

    stripped = {k: v for k, v in credentials.items() if k != "refresh_token"}
    raw = stripped.get("raw")
    if isinstance(raw, dict) and "refresh_token" in raw:
        stripped["raw"] = {k: v for k, v in raw.items() if k != "refresh_token"}
    return stripped