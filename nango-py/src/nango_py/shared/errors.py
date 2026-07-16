"""Shared error protocol for the Python core.

Domain and application layers raise :class:`ApiError` subclasses to signal
HTTP-mappable failures. The transport layer catches them and serializes the
envelope expected by the TypeScript contract (see
``packages/shared/lib/utils/error.manager.ts``).

Kept dependency-free: domain code imports this without FastAPI, Pydantic, or
SQLAlchemy.
"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """Base for errors that map to a stable JSON error envelope.

    Direct-style envelope: ``{error: {code, message?}}`` — matches the
    TypeScript handlers that send ``res.status().send({error: {code, message}})``
    directly (e.g. ``not_found``, ``forbidden``).
    """

    status: int = 500
    code: str = "unknown_error"
    message: str = ""

    def __init__(self) -> None:
        super().__init__(self.message)

    def to_envelope(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code}
        if self.message:
            body["message"] = self.message
        return {"error": body}


class NangoApiError(ApiError):
    """NangoError-style envelope: ``{error: {message, code, payload}}``.

    Matches ``errorManager.errResFromNangoErr`` for errors raised through the
    TypeScript ``NangoError`` path (auth errors), which always include ``payload``
    (defaults to ``{}``) and ``message``.
    """

    payload: dict[str, Any] = {}

    def to_envelope(self) -> dict[str, Any]:
        return {"error": {"message": self.message, "code": self.code, "payload": self.payload}}


class ValidationApiError(ApiError):
    """400 error carrying a list of field issues.

    Wire shape: ``{error: {code, errors: [{code, message, path}]}}`` — matches
    the TypeScript handlers' ``res.status(400).send({error: {code, errors}})``.
    """

    status = 400

    def __init__(self, code: str, errors: list[dict[str, Any]]) -> None:
        self.code = code
        self.errors = errors
        super(ApiError, self).__init__(self.code)

    def to_envelope(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "errors": self.errors}}