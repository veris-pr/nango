"""Connection domain errors.

Both are direct-style envelopes (``{error: {code, message}}``), matching the
TypeScript handlers' ``res.status().send({error: {code, message}})``.
"""

from __future__ import annotations

from nango_py.shared.errors import ApiError


class UnknownProviderConfig(ApiError):
    status = 400
    code = "unknown_provider_config"
    message = "Provider does not exists"


class ConnectionNotFound(ApiError):
    status = 404
    code = "not_found"
    message = "Failed to find connection"