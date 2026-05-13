"""Core user-facing decorators: `@storage` and `@function`.

The `@compute`, `@scale`, `@handler`, and `@shared` decorators were part of
the constraint vocabulary and have been removed per ADR 028. The constraint
keyword arguments on `@storage` (`read_latency`, `write_latency`,
`durability`, `access_pattern`, `write_throughput`, `retention`,
`decommission_policy`, …) are also gone — Phase 2's inference layer derives
infrastructure shape from class shape, not constraints.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypeVar, cast

from skaal.blob import validate_blob_model
from skaal.inference.model import (
    InferredResource,
    ResourceKind,
    SchemaRef,
    SourceLocation,
)
from skaal.types import SecondaryIndex
from skaal.types.compute import Bulkhead, CircuitBreaker, RateLimitPolicy, RetryPolicy

F = TypeVar("F", bound=Callable[..., Any])
C = TypeVar("C", bound=type)
StorageKind = Literal["kv", "blob", "relational"]

_STORAGE_KIND_TO_RESOURCE_KIND: dict[StorageKind, ResourceKind] = {
    "kv": ResourceKind.STORE,
    "blob": ResourceKind.BLOB,
    "relational": ResourceKind.RELATIONAL,
}


def _apply_metadata(target: C, attribute: str, metadata: Any) -> C:
    setattr(target, attribute, metadata)
    return target


def _apply_callable_metadata(target: F, attribute: str, metadata: Any) -> F:
    setattr(target, attribute, metadata)
    return target


def _normalize_storage_kind(kind: StorageKind | str) -> StorageKind:
    normalized = kind.strip().lower()
    if normalized not in {"kv", "blob", "relational"}:
        raise ValueError(f"Unsupported storage kind: {kind!r}")
    return cast(StorageKind, normalized)


def _storage_schema(cls: C, *, kind: StorageKind) -> dict[str, Any]:
    if kind == "blob":
        validate_blob_model(cls)
        try:
            from skaal.storage import _schema_hints

            return _schema_hints(cls)
        except Exception:
            return {}

    if kind == "relational":
        from skaal.relational import _schema_hints as relational_schema_hints
        from skaal.relational import validate_relational_model

        validate_relational_model(cls)
        return relational_schema_hints(cls)

    try:
        from skaal.storage import _schema_hints

        return _schema_hints(cls)
    except Exception:
        return {}


def storage(
    *,
    kind: StorageKind | str = "kv",
    indexes: list[SecondaryIndex] | None = None,
) -> Callable[[C], C]:
    """Declare a Skaal storage class.

    Constraint keyword arguments (latency, durability, access pattern, …)
    have been removed per ADR 028. The inference layer in Phase 2 derives
    storage shape from the class itself; the binding layer in Phase 3
    selects a backend via a fixed defaults table.
    """
    normalized_kind = _normalize_storage_kind(kind)

    def decorator(cls: C) -> C:
        schema = _storage_schema(cls, kind=normalized_kind)
        _apply_metadata(
            cls,
            "__skaal_storage__",
            {
                "kind": normalized_kind,
                "indexes": list(indexes or []) if normalized_kind == "kv" else [],
                "schema": schema,
            },
        )
        idx = tuple(indexes or ()) if normalized_kind == "kv" else ()
        inferred = InferredResource(
            id=InferredResource.id_for(cls),
            kind=_STORAGE_KIND_TO_RESOURCE_KIND[normalized_kind],
            source=SourceLocation.from_object(cls),
            schema_=SchemaRef.from_class(cls),
            indexes=idx,
        )
        return _apply_metadata(cls, "__skaal_inferred__", inferred)

    return decorator


def function(
    *,
    retry: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    rate_limit: RateLimitPolicy | None = None,
    bulkhead: Bulkhead | None = None,
) -> Callable[[F], F]:
    """Declare a Skaal compute function with optional resilience policies.

    Resilience policies (`retry`, `circuit_breaker`, `rate_limit`,
    `bulkhead`) are honoured by the runtime — see
    `skaal.runtime.middleware`.
    """

    def decorator(fn: F) -> F:
        _apply_callable_metadata(
            fn,
            "__skaal_function__",
            {
                "retry": retry,
                "circuit_breaker": circuit_breaker,
                "rate_limit": rate_limit,
                "bulkhead": bulkhead,
            },
        )
        inferred = InferredResource(
            id=InferredResource.id_for(fn),
            kind=ResourceKind.FUNCTION,
            source=SourceLocation.from_object(fn),
        )
        return _apply_callable_metadata(fn, "__skaal_inferred__", inferred)

    return decorator
