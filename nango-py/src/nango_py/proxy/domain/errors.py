"""Proxy errors.

Codes mirror ``ProxyErrorCode`` in
``packages/shared/lib/services/proxy/utils.ts``. Direct-style envelope
(``{error: {code, message}}``) for the handler-emitted ones.
"""

from __future__ import annotations

from nango_py.shared.errors import ApiError


class ProxyError(ApiError):
    """A proxy-domain error mapped to a stable HTTP envelope.

    Carries the TS ``code`` (e.g. ``missing_api_url``, ``unsupported_auth``).
    """

    def __init__(self, code: str, message: str = "", *, status: int = 400) -> None:
        self.code = code
        self.status = status
        self.message = message or code
        super(ApiError, self).__init__(self.code)