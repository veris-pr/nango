"""Integrations domain errors."""

from __future__ import annotations

from nango_py.shared.errors import ApiError


class IntegrationNotFound(ApiError):
    status = 404
    code = "not_found"

    def __init__(self, unique_key: str) -> None:
        self.unique_key = unique_key
        self.message = f'Integration "{unique_key}" does not exist'
        super().__init__()


class ProviderNotFound(ApiError):
    status = 404
    code = "not_found"

    def __init__(self, provider: str) -> None:
        self.message = f"Unknown provider {provider}"
        super().__init__()


def integration_already_exists(provider_config_key: str) -> ApiError:
    class _Err(ApiError):
        status = 400
        code = "duplicate_unique_key"
        message = f"Integration with unique_key '{provider_config_key}' already exists"

    return _Err()