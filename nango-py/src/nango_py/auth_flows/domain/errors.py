"""Auth flow errors."""

from __future__ import annotations

from nango_py.shared.errors import ApiError


class UnknownIntegrationConfig(ApiError):
    status = 404
    code = "unknown_provider_config"
    message = "Provider config not found"


class UnknownProviderTemplate(ApiError):
    status = 404
    code = "unknown_provider_template"
    message = "Unknown provider"


class InvalidAuthMode(ApiError):
    status = 400
    code = "invalid_auth_mode"

    def __init__(self, message: str = "Provider does not support this auth mode") -> None:
        self.message = message
        super(ApiError, self).__init__(self.code)


class ConnectionTestFailed(ApiError):
    status = 400
    code = "connection_test_failed"

    def __init__(self, message: str) -> None:
        self.message = message
        super(ApiError, self).__init__(self.code)