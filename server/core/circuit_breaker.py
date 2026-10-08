from __future__ import annotations

import enum
import logging
import time

from server.core.logging_config import log_event

logger = logging.getLogger(__name__)


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Simple circuit breaker for external service calls.

    After ``failure_threshold`` consecutive failures the circuit opens and
    rejects calls for ``recovery_timeout`` seconds.  After that window one
    trial call is allowed (half-open).  If it succeeds the circuit closes;
    if it fails the circuit reopens for another timeout period.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        *,
        name: str = "circuit-breaker",
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._name = name

        self._state = CircuitState.CLOSED
        self._consecutive_failures: int = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        """Return the *effective* state, accounting for recovery timeout."""
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    def allow_request(self) -> bool:
        """Return True if a request should be attempted."""
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return True
        # OPEN
        return False

    def record_success(self) -> None:
        """Record a successful call.  Resets the breaker to closed."""
        prev = self._state
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        if prev != CircuitState.CLOSED:
            log_event(logger, "circuit_closed", breaker=self._name, previous_state=prev.value)

    def record_failure(self) -> None:
        """Record a failed call.  Opens the breaker after threshold failures."""
        self._consecutive_failures += 1
        self._last_failure_time = time.monotonic()

        if self._consecutive_failures >= self._failure_threshold:
            prev = self._state
            self._state = CircuitState.OPEN
            if prev != CircuitState.OPEN:
                log_event(
                    logger, "circuit_opened", level=logging.WARNING,
                    breaker=self._name, consecutive_failures=self._consecutive_failures,
                    recovery_timeout_s=self._recovery_timeout,
                )
        elif self._state == CircuitState.HALF_OPEN:
            # Trial call in half-open failed -> reopen
            self._state = CircuitState.OPEN
            log_event(logger, "circuit_reopened", level=logging.WARNING, breaker=self._name)
