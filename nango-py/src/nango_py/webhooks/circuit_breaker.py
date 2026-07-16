"""Circuit breaker for webhook delivery.

Mirrors the TS circuit breaker pattern. When a URL fails repeatedly within a
window, the circuit opens and blocks requests for a cooldown period.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


class CircuitOpenError(Exception):
    def __init__(self, key: str) -> None:
        super().__init__(f"circuit_breaker_open:{key}")
        self.key = key


@dataclass
class _CircuitState:
    failures: int
    window_started_at: float
    open_until: float | None = None


class InMemoryCircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        window_seconds: float = 60,
        cooldown_seconds: float = 30,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._window = window_seconds
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._states: dict[str, _CircuitState] = {}

    def before_request(self, key: str) -> None:
        state = self._states.get(key)
        if state is None or state.open_until is None:
            return
        now = self._clock()
        if now < state.open_until:
            raise CircuitOpenError(key)
        self._states[key] = _CircuitState(failures=0, window_started_at=now)

    def record_success(self, key: str) -> None:
        self._states.pop(key, None)

    def record_failure(self, key: str) -> None:
        now = self._clock()
        state = self._states.get(key)
        if state is None or now - state.window_started_at > self._window:
            state = _CircuitState(failures=0, window_started_at=now)
        failures = state.failures + 1
        open_until = now + self._cooldown if failures >= self._threshold else None
        self._states[key] = _CircuitState(
            failures=failures, window_started_at=state.window_started_at, open_until=open_until
        )