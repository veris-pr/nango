from __future__ import annotations

import time
from collections.abc import Callable, Iterable

DEFAULT_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError)


def retry[T](
    fn: Callable[[], T],
    *,
    max_attempts: int,
    delay_seconds: float = 0,
    retryable_exceptions: tuple[type[Exception], ...] = DEFAULT_RETRYABLE_EXCEPTIONS,
    retryable_status_codes: Iterable[int] = DEFAULT_RETRYABLE_STATUS_CODES,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    retryable_statuses = frozenset(retryable_status_codes)
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt == max_attempts or not is_retryable_error(
                exc,
                retryable_exceptions=retryable_exceptions,
                retryable_status_codes=retryable_statuses,
            ):
                raise
            sleep(delay_seconds)

    raise RuntimeError("unreachable")


def is_retryable_error(
    exc: Exception,
    *,
    retryable_exceptions: tuple[type[Exception], ...] = DEFAULT_RETRYABLE_EXCEPTIONS,
    retryable_status_codes: Iterable[int] = DEFAULT_RETRYABLE_STATUS_CODES,
) -> bool:
    if isinstance(exc, retryable_exceptions):
        return True

    status_code = status_code_from_exception(exc)
    return status_code in retryable_status_codes if status_code is not None else False


def status_code_from_exception(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    direct_status_code = getattr(exc, "status_code", None)
    if isinstance(direct_status_code, int):
        return direct_status_code

    return None
