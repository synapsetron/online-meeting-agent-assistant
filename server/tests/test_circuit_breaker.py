from __future__ import annotations

import time
from unittest.mock import patch

from server.core.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreakerTransitions:
    def test_starts_closed(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_stays_closed_below_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_opens_at_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_open_to_half_open_after_timeout(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=5.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Simulate time passing beyond recovery timeout
        with patch.object(time, "monotonic", return_value=time.monotonic() + 10):
            assert cb.state == CircuitState.HALF_OPEN
            assert cb.allow_request() is True

    def test_half_open_to_closed_on_success(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=5.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        # Simulate time passing to enter half-open
        base = time.monotonic()
        with patch.object(time, "monotonic", return_value=base + 10):
            assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_half_open_to_open_on_failure(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=5.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        # Simulate time passing to enter half-open
        base = time.monotonic()
        with patch.object(time, "monotonic", return_value=base + 10):
            assert cb.state == CircuitState.HALF_OPEN

        # Record another failure (trial call failed) -- this reopens the circuit
        # and resets _last_failure_time to "now", so the 5s timeout restarts.
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # Counter was reset, so a single new failure does not open
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_open_rejects_multiple_requests(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.allow_request() is False
        assert cb.allow_request() is False
        assert cb.allow_request() is False
