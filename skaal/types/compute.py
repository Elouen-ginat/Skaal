"""Resilience policies attached to `@app.function`.

`Compute`, `Scale`, `ScaleStrategy`, and `ComputeType` were part of the
constraint-solver vocabulary and have been removed per ADR 028.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class RetryPolicy:
    """Retry-with-backoff and optional idempotency for a function."""

    max_attempts: int = 3
    backoff: Literal["fixed", "linear", "exponential"] = "exponential"
    base_delay_ms: int = 100
    max_delay_ms: int = 30_000
    idempotency_key: str | None = None


@dataclass
class CircuitBreaker:
    """Open the circuit after N consecutive failures; probe after recovery_timeout_ms."""

    failure_threshold: int = 5
    recovery_timeout_ms: int = 10_000
    fallback: str | None = None


@dataclass
class RateLimitPolicy:
    """Token-bucket rate limiting, optionally scoped per-client or per-argument."""

    requests_per_second: float
    burst: int = 1
    scope: str = "global"


@dataclass
class Bulkhead:
    """Limit concurrent calls; callers block up to `max_wait_ms` then fail fast."""

    max_concurrent_calls: int
    max_wait_ms: int = 0
