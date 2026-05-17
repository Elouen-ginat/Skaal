"""Resilience middleware chain for `@app.function` invocations.

The runtime wraps every user callable in the chain ``retry →
circuit_breaker → rate_limit → bulkhead → user_callable``. The four
policy classes survive unchanged from `skaal.types.compute`; this
module applies them as composable async wrappers backed by the
established libraries already in the dependency tree:

- ``tenacity`` for the retry-with-backoff loop.
- ``pybreaker`` for the circuit-breaker state machine.
- ``asyncio.Semaphore`` for the bulkhead.
- A small token-bucket for the rate limiter (no obvious off-the-shelf
  fit in the dependency set; the implementation is ~20 lines).

The chain is intentionally minimal — the Phase 4 cut focuses on the
correctness contract (each policy is honoured exactly once and in the
right order) rather than the full backpressure / observability surface
that ADR 028 §6.7 spells out. Those richer behaviours land alongside
the deploy-time observability work in a later phase.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

import pybreaker
import tenacity

from skaal.types.compute import (
    Bulkhead,
    CircuitBreaker,
    RateLimit,
    Retry,
)

R = TypeVar("R")
Handler = Callable[..., Awaitable[R]]


class _RateLimitBucket:
    """Token-bucket counter for a single function (no per-arg sharding here)."""

    __slots__ = ("burst", "last_refill", "rate", "tokens")

    def __init__(self, rate: float, burst: int) -> None:
        self.tokens: float = float(burst)
        self.last_refill: float = time.monotonic()
        self.rate: float = float(rate)
        self.burst: float = float(burst)

    def acquire(self) -> bool:
        now: float = time.monotonic()
        elapsed: float = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


def _tenacity_wait(policy: Retry) -> tenacity.wait.wait_base:
    base_s: float = policy.base_delay_ms / 1000.0
    max_s: float = policy.max_delay_ms / 1000.0
    if policy.backoff == "fixed":
        return tenacity.wait_fixed(base_s)
    if policy.backoff == "linear":
        return tenacity.wait_incrementing(start=base_s, increment=base_s, max=max_s)
    return tenacity.wait_exponential(multiplier=base_s, max=max_s)


def wrap_resilience(
    handler: Handler[R],
    *,
    retry: Retry | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    rate_limit: RateLimit | None = None,
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
    sem: asyncio.Semaphore = asyncio.Semaphore(policy.max_concurrent_calls)
    timeout: float | None = policy.max_wait_ms / 1000.0 if policy.max_wait_ms > 0 else None

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


def _with_rate_limit(handler: Handler[R], policy: RateLimit) -> Handler[R]:
    bucket: _RateLimitBucket = _RateLimitBucket(policy.requests_per_second, policy.burst)

    async def wrapper(*args: Any, **kwargs: Any) -> R:
        if not bucket.acquire():
            raise RuntimeError("rate limit exceeded")
        return await handler(*args, **kwargs)

    return wrapper


def _with_circuit_breaker(handler: Handler[R], policy: CircuitBreaker) -> Handler[R]:
    breaker: pybreaker.CircuitBreaker = pybreaker.CircuitBreaker(
        fail_max=policy.failure_threshold,
        reset_timeout=policy.recovery_timeout_ms / 1000.0,
    )

    async def wrapper(*args: Any, **kwargs: Any) -> R:
        # `pybreaker.call_async` requires Tornado in its current release;
        # we drive the same state machine manually through the
        # public-ish hooks (`state.before_call`, `state.on_success` /
        # `state.on_failure`, plus the storage's counter API). The flow
        # mirrors `CircuitBreakerState.call` for the sync entry point.
        state: pybreaker.CircuitBreakerState = breaker.state
        try:
            state.before_call(handler, *args, **kwargs)
        except pybreaker.CircuitBreakerError as exc:
            raise RuntimeError("circuit breaker open") from exc

        try:
            result: R = await handler(*args, **kwargs)
        except Exception as exc:
            breaker._state_storage.increment_counter()
            listeners: list[Any] = cast(Any, breaker).listeners
            for fail_listener in listeners:
                fail_listener.failure(breaker, exc)
            try:
                state.on_failure(exc)
            except pybreaker.CircuitBreakerError as breaker_exc:
                raise RuntimeError("circuit breaker open") from breaker_exc
            raise
        breaker._state_storage.reset_counter()
        listeners = cast(Any, breaker).listeners
        for success_listener in listeners:
            success_listener.success(breaker)
        state.on_success()
        return result

    return wrapper


def _with_retry(handler: Handler[R], policy: Retry) -> Handler[R]:
    retrying: tenacity.AsyncRetrying = tenacity.AsyncRetrying(
        stop=tenacity.stop_after_attempt(policy.max_attempts),
        wait=_tenacity_wait(policy),
        retry=tenacity.retry_if_exception_type(Exception),
        reraise=True,
    )

    async def wrapper(*args: Any, **kwargs: Any) -> R:
        result: R = await retrying.wraps(handler)(*args, **kwargs)
        return result

    return wrapper


__all__ = ["wrap_resilience"]
