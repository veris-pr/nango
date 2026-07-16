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
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be greater than 0")
        if cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be greater than 0")

        self._failure_threshold = failure_threshold
        self._window_seconds = window_seconds
        self._cooldown_seconds = cooldown_seconds
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
        if state is None or now - state.window_started_at > self._window_seconds:
            state = _CircuitState(failures=0, window_started_at=now)

        failures = state.failures + 1
        open_until = now + self._cooldown_seconds if failures >= self._failure_threshold else None
        self._states[key] = _CircuitState(
            failures=failures,
            window_started_at=state.window_started_at,
            open_until=open_until,
        )
