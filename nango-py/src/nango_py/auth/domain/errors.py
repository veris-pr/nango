"""Auth domain errors.

Codes and messages mirror the TypeScript ``NangoError`` cases in
``packages/shared/lib/utils/error.ts`` exactly so the wire envelope matches.
"""

from __future__ import annotations

from nango_py.shared.errors import ApiError, NangoApiError


class MissingAuthHeader(NangoApiError):
    status = 401
    code = "missing_auth_header"
    message = "Authentication failed. The request is missing the Authorization header."


class MalformedAuthHeader(NangoApiError):
    status = 401
    code = "malformed_auth_header"
    message = "Authentication failed. The Authorization header is malformed."


class InvalidSecretKeyFormat(NangoApiError):
    status = 401
    code = "invalid_secret_key_format"
    message = "Authentication failed. The provided secret key is not a UUID v4."


class UnknownAccount(NangoApiError):
    status = 401
    code = "unknown_account"
    message = "Authentication failed. The provided authorization header does not match any account."


class Forbidden(ApiError):
    status = 403
    code = "forbidden"

    def __init__(self, required: tuple[str, ...]) -> None:
        self.required = required
        if len(required) == 1:
            self.message = f"Insufficient scope. Required: {required[0]}"
        else:
            self.message = (
                f"Insufficient scope. Required one of: {' or '.join(required)}"
            )
        super().__init__()