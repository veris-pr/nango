"""Keystore errors."""

from __future__ import annotations

from nango_py.shared.errors import ApiError


class PrivateKeyNotFound(ApiError):
    status = 401
    code = "not_found"
    message = "Private key not found"


class PrivateKeyCreationFailed(ApiError):
    status = 500
    code = "creation_failed"
    message = "Failed to create private key"