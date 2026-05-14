"""Serialization helpers for the runtime-metadata fields on `ResourceOverrides`.

`@app.function` and `@app.schedule` accept rich Python objects (dataclass
resilience policies, `Cron` / `Every` triggers). The inference layer only
carries JSON-shaped data on `ResourceOverrides.resilience` / `.trigger`,
so the decorator collapses the user objects into dicts here and the
runtime adapters reconstruct them.

The shapes are deliberately narrow so a future ADR can move them to
typed pydantic models without churning every call site.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skaal.schedule import Cron, Every
    from skaal.types.compute import Bulkhead, CircuitBreaker, RateLimitPolicy, RetryPolicy


def encode_resilience(
    *,
    retry: RetryPolicy | None,
    circuit_breaker: CircuitBreaker | None,
    rate_limit: RateLimitPolicy | None,
    bulkhead: Bulkhead | None,
) -> dict[str, Any] | None:
    """Pack the four resilience-policy dataclasses into a JSON-shaped dict.

    Returns ``None`` when every policy is absent so the override stays
    unset rather than carrying ``{}`` placeholders.
    """
    payload: dict[str, Any] = {}
    if retry is not None and is_dataclass(retry):
        payload["retry"] = asdict(retry)
    if circuit_breaker is not None and is_dataclass(circuit_breaker):
        payload["circuit_breaker"] = asdict(circuit_breaker)
    if rate_limit is not None and is_dataclass(rate_limit):
        payload["rate_limit"] = asdict(rate_limit)
    if bulkhead is not None and is_dataclass(bulkhead):
        payload["bulkhead"] = asdict(bulkhead)
    return payload or None


def decode_resilience(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Reconstruct dataclass instances from the encoded resilience payload."""
    if not payload:
        return {}
    from skaal.types.compute import (
        Bulkhead,
        CircuitBreaker,
        RateLimitPolicy,
        RetryPolicy,
    )

    out: dict[str, Any] = {}
    if (raw := payload.get("retry")) is not None:
        out["retry"] = RetryPolicy(**raw)
    if (raw := payload.get("circuit_breaker")) is not None:
        out["circuit_breaker"] = CircuitBreaker(**raw)
    if (raw := payload.get("rate_limit")) is not None:
        out["rate_limit"] = RateLimitPolicy(**raw)
    if (raw := payload.get("bulkhead")) is not None:
        out["bulkhead"] = Bulkhead(**raw)
    return out


def encode_trigger(trigger: object) -> dict[str, Any] | None:
    """Pack a `Cron` / `Every` trigger into a JSON-shaped dict."""
    from skaal.schedule import Cron, Every

    if isinstance(trigger, Every):
        return {"kind": "every", "interval": trigger.interval}
    if isinstance(trigger, Cron):
        return {"kind": "cron", "expression": trigger.expression}
    return None


def decode_trigger(payload: dict[str, Any] | None) -> Cron | Every | None:
    """Reconstruct a `Cron` / `Every` from an encoded trigger payload."""
    if not payload:
        return None
    from skaal.schedule import Cron, Every

    kind = payload.get("kind")
    if kind == "every":
        return Every(interval=payload["interval"])
    if kind == "cron":
        return Cron(expression=payload["expression"])
    return None
