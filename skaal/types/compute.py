"""Resilience policies attached to `@app.function`.

`Compute`, `Scale`, `ScaleStrategy`, and `ComputeType` were part of the
constraint-solver vocabulary and have been removed per ADR 028.

Phase 4 (ADR 032 §4.9) reshapes these from `@dataclass` to frozen
pydantic models so they ride directly on
`InferredResource.overrides.resilience` without dict round-tripping.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Retry(BaseModel):
    """Retry-with-backoff and optional idempotency for a function."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_attempts: int = 3
    backoff: Literal["fixed", "linear", "exponential"] = "exponential"
    base_delay_ms: int = 100
    max_delay_ms: int = 30_000
    idempotency_key: str | None = None


class CircuitBreaker(BaseModel):
    """Open the circuit after N consecutive failures; probe after recovery_timeout_ms."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    failure_threshold: int = 5
    recovery_timeout_ms: int = 10_000
    fallback: str | None = None


class RateLimit(BaseModel):
    """Token-bucket rate limiting, optionally scoped per-client or per-argument."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requests_per_second: float
    burst: int = 1
    scope: str = "global"


class Bulkhead(BaseModel):
    """Limit concurrent calls; callers block up to `max_wait_ms` then fail fast."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_concurrent_calls: int
    max_wait_ms: int = 0


class ResiliencePolicies(BaseModel):
    """The four-policy resilience envelope attached to a function-shaped resource.

    Lives on `ResourceOverrides.resilience` (ADR 032 §4.4); the runtime
    middleware chain reads each policy and wraps the user callable in
    the order ``retry → circuit_breaker → rate_limit → bulkhead``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    retry: Retry | None = None
    circuit_breaker: CircuitBreaker | None = None
    rate_limit: RateLimit | None = None
    bulkhead: Bulkhead | None = None

    @property
    def is_empty(self) -> bool:
        """Return ``True`` when every policy slot is unset."""
        return (
            self.retry is None
            and self.circuit_breaker is None
            and self.rate_limit is None
            and self.bulkhead is None
        )
