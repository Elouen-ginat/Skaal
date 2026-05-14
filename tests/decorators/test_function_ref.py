"""Tests for the `FunctionRef[P, R]` typed return (ADR 032 §4.7)."""

from __future__ import annotations

import inspect

from skaal import FunctionRef
from skaal.inference.model import (
    InferredResource,
    ResourceKind,
    ResourceOverrides,
    SourceLocation,
)


async def _example(x: int, y: str = "ok") -> str:
    return f"{x}-{y}"


def _build_ref(*, overrides: ResourceOverrides | None = None) -> FunctionRef[..., str]:
    overrides = overrides or ResourceOverrides()
    inferred = InferredResource(
        id="m:_example",
        kind=ResourceKind.FUNCTION,
        source=SourceLocation.from_object(_example),
        overrides=overrides,
    )
    return FunctionRef(
        _example, id="m:_example", overrides=overrides, inferred=inferred
    )


def test_function_ref_is_callable_and_forwards_to_wrapped() -> None:
    ref = _build_ref()
    assert callable(ref)
    assert ref.__wrapped__ is _example


def test_function_ref_forwards_name_via_getattr() -> None:
    # `__module__` and `__qualname__` resolve through the class hierarchy and
    # cannot be transparently forwarded without a metaclass. `__name__` is
    # not a class attribute on `FunctionRef`, so the `__getattr__` fallback
    # forwards it correctly — that is the contract the inference walker
    # depends on (it reads `__name__` for resource IDs).
    ref = _build_ref()
    assert ref.__name__ == "_example"


def test_function_ref_signature_proxy() -> None:
    ref = _build_ref()
    sig = inspect.signature(ref)
    assert list(sig.parameters.keys()) == ["x", "y"]


def test_function_ref_carries_id_and_overrides() -> None:
    ref = _build_ref(overrides=ResourceOverrides(backend="redis"))
    assert ref.id == "m:_example"
    assert ref.overrides.backend == "redis"


def test_function_ref_exposes_inferred_resource() -> None:
    ref = _build_ref(overrides=ResourceOverrides(backend="redis"))
    assert ref.__skaal_inferred__.kind == ResourceKind.FUNCTION
    assert ref.__skaal_inferred__.overrides.backend == "redis"
