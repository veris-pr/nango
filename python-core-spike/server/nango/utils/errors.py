from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    path: tuple[str | int, ...]

    def to_api_error(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, "path": list(self.path)}


class ApplicationError(Exception):
    def __init__(
        self,
        code: str,
        *,
        message: str | None = None,
        status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR,
        errors: tuple[ValidationIssue, ...] = (),
        payload: Any | None = None,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message
        self.status_code = int(status_code)
        self.errors = errors
        self.payload = payload

    def to_api_error(self) -> dict[str, dict[str, object]]:
        error: dict[str, object] = {"code": self.code}
        if self.message is not None:
            error["message"] = self.message
        if self.errors:
            error["errors"] = [issue.to_api_error() for issue in self.errors]
        if self.payload is not None:
            error["payload"] = self.payload
        return {"error": error}
