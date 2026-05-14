"""Tests for the `FunctionRef[P, R]` typed return (ADR 032 §4.7)."""

from __future__ import annotations

import inspect

from skaal import FunctionRef
from skaal.inference.model import ResourceOverrides


async def _example(x: int, y: str = "ok") -> str:
    return f"{x}-{y}"


def test_function_ref_is_callable_and_forwards_to_wrapped() -> None:
    ref: FunctionRef[..., str] = FunctionRef(
        _example, id="m:_example", overrides=ResourceOverrides()
    )
    assert callable(ref)
    assert ref.__wrapped__ is _example


def test_function_ref_forwards_name_via_getattr() -> None:
    # `__module__` and `__qualname__` resolve through the class hierarchy and
    # cannot be transparently forwarded without a metaclass. `__name__` is
    # not a class attribute on `FunctionRef`, so the `__getattr__` fallback
    # forwards it correctly — that is the contract the legacy consumers care
    # about (the inference walker reads `__name__` for resource IDs).
    ref: FunctionRef[..., str] = FunctionRef(
        _example, id="m:_example", overrides=ResourceOverrides()
    )
    assert ref.__name__ == "_example"


def test_function_ref_signature_proxy() -> None:
    ref: FunctionRef[..., str] = FunctionRef(
        _example, id="m:_example", overrides=ResourceOverrides()
    )
    sig = inspect.signature(ref)
    assert list(sig.parameters.keys()) == ["x", "y"]


def test_function_ref_carries_id_and_overrides() -> None:
    overrides = ResourceOverrides(backend="redis")
    ref: FunctionRef[..., str] = FunctionRef(
        _example, id="m:_example", overrides=overrides
    )
    assert ref.id == "m:_example"
    assert ref.overrides.backend == "redis"
