"""Tests for the local runtime's resilience middleware."""

from __future__ import annotations

import asyncio

import pytest

from skaal.runtime.middleware import wrap_resilience
from skaal.types.compute import (
    Bulkhead,
    CircuitBreaker,
    RateLimitPolicy,
    RetryPolicy,
)


async def test_no_policy_is_passthrough() -> None:
    calls = 0

    async def handler() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    wrapped = wrap_resilience(handler)
    assert await wrapped() == "ok"
    assert calls == 1


async def test_retry_attempts_until_success() -> None:
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("boom")
        return "ok"

    wrapped = wrap_resilience(
        flaky,
        retry=RetryPolicy(max_attempts=5, base_delay_ms=0, max_delay_ms=0),
    )
    assert await wrapped() == "ok"
    assert attempts == 3


async def test_retry_gives_up_after_max_attempts() -> None:
    attempts = 0

    async def always_fails() -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("nope")

    wrapped = wrap_resilience(
        always_fails,
        retry=RetryPolicy(max_attempts=3, base_delay_ms=0, max_delay_ms=0),
    )
    with pytest.raises(RuntimeError, match="nope"):
        await wrapped()
    assert attempts == 3


async def test_circuit_breaker_opens_after_threshold() -> None:
    async def failing() -> None:
        raise RuntimeError("boom")

    wrapped = wrap_resilience(
        failing,
        circuit_breaker=CircuitBreaker(failure_threshold=2, recovery_timeout_ms=60_000),
    )
    with pytest.raises(RuntimeError, match="boom"):
        await wrapped()
    with pytest.raises(RuntimeError, match="boom"):
        await wrapped()
    with pytest.raises(RuntimeError, match="circuit breaker open"):
        await wrapped()


async def test_rate_limit_rejects_excess_calls() -> None:
    calls = 0

    async def handler() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    wrapped = wrap_resilience(
        handler,
        rate_limit=RateLimitPolicy(requests_per_second=0.001, burst=1),
    )
    assert await wrapped() == "ok"
    with pytest.raises(RuntimeError, match="rate limit"):
        await wrapped()


async def test_bulkhead_serialises_calls() -> None:
    running = 0
    peak = 0

    async def slow() -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1

    wrapped = wrap_resilience(slow, bulkhead=Bulkhead(max_concurrent_calls=1))
    await asyncio.gather(*(wrapped() for _ in range(5)))
    assert peak == 1
