from __future__ import annotations

from fastapi import Header, HTTPException

from nango.persist.models import PersistAuthContext


async def persist_auth(
    environment_id: int,
    authorization: str | None = Header(default=None),
) -> PersistAuthContext:
    """Placeholder for future environment secret authentication.

    The TypeScript service resolves the bearer token to an account and verifies it
    belongs to the requested environment. The Python port intentionally only
    validates that callers send a bearer token so route contracts can be exercised
    without adding account storage or production auth.
    """
    if authorization is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "missing_auth_header",
                    "message": "Missing authorization header",
                }
            },
        )

    prefix = "Bearer "
    if not authorization.startswith(prefix) or authorization == prefix:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "malformed_auth_header",
                    "message": "Malformed authorization header. Expected `Bearer SECRET_KEY`",
                }
            },
        )

    return PersistAuthContext(
        environment_id=environment_id,
        token=authorization.removeprefix(prefix),
    )
