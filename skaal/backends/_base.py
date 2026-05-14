"""Typed `Backend` token base class (ADR 028 §6.12, ADR 031 §3.1).

Each concrete backend in the registry is represented by a `Backend` subclass —
a real Python class that user code can import and pass as the second generic
parameter to `Store[T, B]` / `Relational[T, B]` / `BlobStore[B]` / `Channel[T, B]`
once Phase 4 wires that syntax.

The token carries:

- ``name`` — the registry-facing string form (matches `BackendEntry.token.name`
  and the string used inside ``skaal.toml`` env overrides).
- ``kinds`` — the `ResourceKind` values (as strings) this backend can satisfy.
- ``NativeClient`` — the concrete SDK type returned by `.native()` on a
  type-pinned primitive. Phase 3 narrows this to ``object`` for backends whose
  SDK lives behind an optional extra; Phase 5 specialises it under
  ``TYPE_CHECKING`` so Pylance still sees the real type.

Why this is a base class and not a `Protocol`:

1. ``Generic[NativeClientT]`` carries the typed escape (`B.NativeClient`) the
   IDE follows when the user hovers ``Cache.native()`` — protocols cannot
   declare a parameterised class variable.
2. ``isinstance(x, Backend)`` works at runtime (the registry uses it to
   validate token classes when loading TOML overrides).
3. The base class owns no state and no methods; concrete subclasses are pure
   class bodies, so the inheritance cost is zero at runtime.
"""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar

NativeClientT = TypeVar("NativeClientT")


class Backend(Generic[NativeClientT]):
    """Base class for every backend type token (ADR 028 §6.12).

    Subclasses populate the three class variables below; the framework never
    instantiates them. They are imported at user-code sites (`from
    skaal.backends.redis import Redis`) and used as the second generic
    parameter on primitive classes (`Store[User, Redis]`) once Phase 4 wires
    that syntax. The same token is the registry key (`token.name`) and the
    binder's source of truth for `kinds` and `targets` checks.
    """

    name: ClassVar[str] = ""
    kinds: ClassVar[frozenset[str]] = frozenset()
    NativeClient: ClassVar[type[Any]] = object
