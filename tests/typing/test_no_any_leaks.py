"""No public symbol's annotated return type leaks `Any` (ADR 028 §6.13.3).

The check is intentionally narrow: it walks every name in `skaal.__all__`,
resolves its type hints, and fails if a *top-level* return annotation
collapses to `typing.Any`. It does not chase nested generics — `dict[str,
Any]` is fine, `-> Any` is not.

Symbols without annotations (legacy pydantic class-method overloads, the
`types` namespace module) are skipped — the gate only catches explicit
``-> Any`` regressions on the documented public surface.
"""

from __future__ import annotations

import inspect
import types
from typing import Any, get_type_hints

import pytest

import skaal


def _public_symbols() -> list[tuple[str, object]]:
    return [(name, getattr(skaal, name)) for name in sorted(skaal.__all__)]


def _expected_any_returns() -> set[str]:
    """Symbols whose return type is intentionally `Any`.

    The typed `.native()` escape (`Store.native`, `Table.native`,
    `BlobStore.native`, `Topic.native`) returns `Any` in Phase 5a;
    Phase 5b narrows it via per-token overloads.

    ``Module.attach`` and ``App.attach`` are extension hooks: they accept
    a user-supplied component object and return whatever that component's
    register API yields, by design. ``Module.invoke`` returns the result
    of a user-supplied function; the alternative is a sweeping change to
    `FunctionRef` ParamSpec inference. Both are deferred to Phase 5b.

    The `FunctionRef` dunder accessors forward to the wrapped callable
    and intentionally pass through any attribute resolution.
    """
    return {
        "Store.native",
        "Table.native",
        "BlobStore.native",
        "Topic.native",
        "FunctionRef.__getattr__",
        "FunctionRef.__call__",
        "Module.attach",
        "Module.invoke",
        "App.attach",
        "App.invoke",
    }


@pytest.mark.parametrize("name,symbol", _public_symbols())
def test_public_symbol_does_not_return_any(name: str, symbol: object) -> None:
    """Every public callable's annotated return must not be `Any`.

    Classes are walked one level deep — public methods with annotations
    are checked the same way.
    """
    expected = _expected_any_returns()

    if isinstance(symbol, types.ModuleType):
        pytest.skip(f"{name} is a re-exported module")

    if inspect.isfunction(symbol) or inspect.isbuiltin(symbol):
        _check_callable(name, symbol, expected)
        return

    if inspect.isclass(symbol):
        for attr_name, attr in inspect.getmembers(symbol):
            if attr_name.startswith("_") and attr_name not in {"__call__"}:
                continue
            if not callable(attr):
                continue
            qual = f"{name}.{attr_name}"
            _check_callable(qual, attr, expected)


def _check_callable(qual: str, fn: object, expected: set[str]) -> None:
    try:
        hints = get_type_hints(fn)
    except (TypeError, NameError, RecursionError, AttributeError):
        # SQLModel / pydantic forward references on inherited methods can
        # trip `get_type_hints` with recursive Union expansion; skip those
        # — the gate's job is the explicit `-> Any` regression check.
        return
    if "return" not in hints:
        return
    if hints["return"] is Any and qual not in expected:
        pytest.fail(
            f"{qual} returns `Any` but is not in the documented exception set. "
            "Tighten the annotation or add the symbol to `_expected_any_returns()`."
        )
