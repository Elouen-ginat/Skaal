"""Resilience middleware chain for `@app.function` invocations.

The runtime wraps every user callable in the chain ``retry →
circuit_breaker → rate_limit → bulkhead → user_callable``. The four
policy classes survive unchanged from `skaal.types.compute`; this module
applies them as composable async wrappers.

The chain is intentionally minimal — the Phase 4 cut focuses on the
correctness contract (each policy is honoured exactly once and in the
right order) rather than the full backpressure / observability surface
that ADR 028 §6.7 spells out. Those richer behaviours land alongside
the deploy-time observability work in a later phase.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from skaal.types.compute import (
    Bulkhead,
    CircuitBreaker,
    RateLimitPolicy,
    RetryPolicy,
)

R = TypeVar("R")
Handler = Callable[..., Awaitable[R]]


class _CircuitState:
    """Mutable counter shared across calls of a single function."""

    __slots__ = ("failures", "opened_at")

    def __init__(self) -> None:
        self.failures = 0
        self.opened_at: float | None = None


class _RateLimitBucket:
    """Token-bucket counter for a single function (no per-arg sharding here)."""

    __slots__ = ("burst", "last_refill", "rate", "tokens")

    def __init__(self, rate: float, burst: int) -> None:
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self.rate = float(rate)
        self.burst = float(burst)

    def acquire(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


def _delay_seconds(policy: RetryPolicy, attempt: int) -> float:
    base = policy.base_delay_ms / 1000.0
    cap = policy.max_delay_ms / 1000.0
    if policy.backoff == "fixed":
        delay = base
    elif policy.backoff == "linear":
        delay = base * attempt
    else:
        delay = base * (2 ** (attempt - 1))
    delay = min(delay, cap)
    return delay * (0.5 + random.random() / 2.0)


def wrap_resilience(
    handler: Handler[R],
    *,
    retry: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    rate_limit: RateLimitPolicy | None = None,
    bulkhead: Bulkhead | None = None,
) -> Handler[R]:
    """Return ``handler`` wrapped with the configured resilience policies.

    The four policies compose in the order spelled in ADR 032 §4.1: the
    retry loop is the outermost wrapper, the circuit breaker sits inside
    it, then rate limiting, then the bulkhead, then the user callable.
    Passing ``None`` for any policy is a no-op for that layer.
    """
    wrapped: Handler[R] = handler

    if bulkhead is not None:
        wrapped = _with_bulkhead(wrapped, bulkhead)
    if rate_limit is not None:
        wrapped = _with_rate_limit(wrapped, rate_limit)
    if circuit_breaker is not None:
        wrapped = _with_circuit_breaker(wrapped, circuit_breaker)
    if retry is not None:
        wrapped = _with_retry(wrapped, retry)

    return wrapped


def _with_bulkhead(handler: Handler[R], policy: Bulkhead) -> Handler[R]:
    sem = asyncio.Semaphore(policy.max_concurrent_calls)
    timeout = policy.max_wait_ms / 1000.0 if policy.max_wait_ms > 0 else None

    async def wrapper(*args: Any, **kwargs: Any) -> R:
        if timeout is None:
            async with sem:
                return await handler(*args, **kwargs)
        try:
            await asyncio.wait_for(sem.acquire(), timeout=timeout)
        except TimeoutError as exc:
            raise RuntimeError("bulkhead wait exceeded max_wait_ms") from exc
        try:
            return await handler(*args, **kwargs)
        finally:
            sem.release()

    return wrapper


def _with_rate_limit(handler: Handler[R], policy: RateLimitPolicy) -> Handler[R]:
    bucket = _RateLimitBucket(policy.requests_per_second, policy.burst)

    async def wrapper(*args: Any, **kwargs: Any) -> R:
        if not bucket.acquire():
            raise RuntimeError("rate limit exceeded")
        return await handler(*args, **kwargs)

    return wrapper


def _with_circuit_breaker(handler: Handler[R], policy: CircuitBreaker) -> Handler[R]:
    state = _CircuitState()
    recovery = policy.recovery_timeout_ms / 1000.0

    async def wrapper(*args: Any, **kwargs: Any) -> R:
        if state.opened_at is not None:
            if time.monotonic() - state.opened_at < recovery:
                raise RuntimeError("circuit breaker open")
            state.opened_at = None
            state.failures = 0
        try:
            result = await handler(*args, **kwargs)
        except Exception:
            state.failures += 1
            if state.failures >= policy.failure_threshold:
                state.opened_at = time.monotonic()
            raise
        else:
            state.failures = 0
            return result

    return wrapper


def _with_retry(handler: Handler[R], policy: RetryPolicy) -> Handler[R]:
    async def wrapper(*args: Any, **kwargs: Any) -> R:
        last_exc: BaseException | None = None
        for attempt in range(1, policy.max_attempts + 1):
            try:
                return await handler(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt >= policy.max_attempts:
                    raise
                await asyncio.sleep(_delay_seconds(policy, attempt))
        # Unreachable: the loop either returns or raises before exiting.
        assert last_exc is not None
        raise last_exc

    return wrapper


__all__ = ["wrap_resilience"]
