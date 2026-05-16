"""Core user-facing decorators: `@storage`, `@function`, and `@external`.

The `@compute`, `@scale`, `@handler`, and `@shared` decorators were part of
the constraint vocabulary and have been removed per ADR 028. The constraint
keyword arguments on `@storage` (`read_latency`, `write_latency`,
`durability`, `access_pattern`, `write_throughput`, `retention`,
`decommission_policy`, …) are also gone — Phase 2's inference layer derives
infrastructure shape from class shape, not constraints.

Phase 4 (ADR 032) adds the second-generic `Backend` type-pin: when a user
class subclasses `Store[T, Redis]` / `BlobStore[S3]` / `Channel[T, Sqs]`,
the decorator reads the parameterised base and populates
`ResourceOverrides.backend` so the binder pins to that backend. The
`@external` decorator wraps the same machinery with an environment-side
connection lookup. The legacy per-decorator dunders (`storage`, `function`,
`schedule`, `channel`, `job`, `secrets`) are gone: every consumer reads
``__skaal_inferred__``.

Phase 5 (ADR 033) tightens the `@function` decorator's signature so the
wrapped callable's `ParamSpec` and return `TypeVar` flow into
``FunctionRef[P, R]``. Call sites preserve type information through the
decoration, satisfying the ADR 028 §6.13.3 "decorator preserves
signatures" row.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, Generic, Literal, TypeVar, cast, get_args, get_origin

from typing_extensions import ParamSpec

from skaal.backends._base import Backend
from skaal.blob import validate_blob_model
from skaal.inference.model import (
    InferredResource,
    ResourceKind,
    ResourceOverrides,
    SchemaRef,
    SourceLocation,
)
from skaal.types import SecondaryIndex
from skaal.types.compute import (
    Bulkhead,
    CircuitBreaker,
    RateLimitPolicy,
    ResiliencePolicies,
    RetryPolicy,
)

C = TypeVar("C", bound=type)
P = ParamSpec("P")
R = TypeVar("R")
StorageKind = Literal["kv", "blob", "relational"]


class FunctionRef(Generic[P, R]):
    """Typed handle to a ``@app.function``-decorated callable.

    The decorator returns a `FunctionRef` so cross-module call-sites see
    the typed signature without `getattr` indirection (ADR 028 §6.4.2,
    ADR 032 §4.7). Resilience policies, the source location, and the
    canonical resource id all live on ``self.overrides`` /
    ``self.__skaal_inferred__``.

    Attribute access falls through to ``__wrapped__`` so callers that
    read ``__name__`` / ``__module__`` / ``__doc__`` keep working without
    the runtime having to special-case `FunctionRef`.

    Phase 5 (ADR 033) lets ``P`` and ``R`` flow through the decorator
    factory so ``__call__`` preserves the wrapped callable's parameter
    list and return type. For an ``async def signup(user: User) -> User``,
    ``R`` resolves to ``Coroutine[Any, Any, User]`` and
    ``await signup(user)`` reveals ``User``.
    """

    __slots__ = ("__skaal_inferred__", "__wrapped__", "id", "overrides")

    def __init__(
        self,
        fn: Callable[P, Awaitable[R]] | Callable[P, R],
        *,
        id: str,
        overrides: ResourceOverrides,
        inferred: InferredResource,
    ) -> None:
        self.__wrapped__ = fn
        self.id = id
        self.overrides = overrides
        self.__skaal_inferred__ = inferred

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return cast(R, self.__wrapped__(*args, **kwargs))

    def __getattr__(self, name: str) -> Any:
        # Slots block direct setattr but __getattr__ is only invoked when
        # the normal lookup fails — forward everything else to the wrapped
        # callable so consumers reading ``__name__`` / ``__module__`` /
        # ``__doc__`` keep working.
        wrapped = object.__getattribute__(self, "__wrapped__")
        return getattr(wrapped, name)

    @property
    def __signature__(self) -> inspect.Signature:
        return inspect.signature(self.__wrapped__)


def _extract_backend_pin(cls: type) -> type[Backend[Any]] | None:
    """Return the `Backend` subclass pinned via the class's parameterised base.

    Two capture paths share the same return contract:

    * `Store[T, B]` / `BlobStore[B]` / `Channel[T, B]` keep the
      parametrisation visible on ``__orig_bases__``; the walk below
      picks the `Backend` subclass out of the generic args directly.
    * `Relational[B]` flows through `SQLModelMetaclass`, which
      overwrites ``__orig_bases__`` on subclasses. The token is stashed
      on ``__skaal_backend_pin__`` by `Relational.__class_getitem__`
      instead; subclasses inherit it via the normal MRO.

    ``Backend`` itself — the default value of the ``B`` `TypeVar` on
    every primitive — is ignored so un-pinned declarations
    (``Store[User]``) report no pin. Returns ``None`` when no pin is
    present.
    """
    pinned: Any = getattr(cls, "__skaal_backend_pin__", None)
    if isinstance(pinned, type) and issubclass(pinned, Backend) and pinned is not Backend:
        return cast("type[Backend[Any]]", pinned)

    bases: tuple[Any, ...] = getattr(cls, "__orig_bases__", ())
    for base in bases:
        args = get_args(base)
        for arg in args:
            origin = get_origin(arg)
            candidate: Any = origin if isinstance(origin, type) else arg
            if (
                isinstance(candidate, type)
                and issubclass(candidate, Backend)
                and candidate is not Backend
            ):
                return cast("type[Backend[Any]]", candidate)
    return None


_STORAGE_KIND_TO_RESOURCE_KIND: dict[StorageKind, ResourceKind] = {
    "kv": ResourceKind.STORE,
    "blob": ResourceKind.BLOB,
    "relational": ResourceKind.RELATIONAL,
}


def _normalize_storage_kind(kind: StorageKind | str) -> StorageKind:
    normalized = kind.strip().lower()
    if normalized not in {"kv", "blob", "relational"}:
        raise ValueError(f"Unsupported storage kind: {kind!r}")
    return cast(StorageKind, normalized)


def _validate_storage_class(cls: type, *, kind: StorageKind) -> None:
    """Run the kind-specific structural validation for a storage class.

    Phase 1 used the schema-hints helpers as the validation entry point;
    Phase 4 keeps the validation but no longer surfaces the hints onto
    the class — the inference layer's `SchemaRef` is the canonical source.
    """
    if kind == "blob":
        validate_blob_model(cls)
        return
    if kind == "relational":
        from skaal.relational import validate_relational_model

        validate_relational_model(cls)


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
        _validate_storage_class(cls, kind=normalized_kind)
        idx = tuple(indexes or ()) if normalized_kind == "kv" else ()
        pinned_token = _extract_backend_pin(cls)
        overrides = (
            ResourceOverrides(backend=pinned_token.name)
            if pinned_token is not None
            else ResourceOverrides()
        )
        inferred = InferredResource(
            id=InferredResource.id_for(cls),
            kind=_STORAGE_KIND_TO_RESOURCE_KIND[normalized_kind],
            source=SourceLocation.from_object(cls),
            schema_=SchemaRef.from_class(cls),  # pyright: ignore[reportCallIssue]
            indexes=idx,
            overrides=overrides,
        )
        cls.__skaal_inferred__ = inferred  # type: ignore[attr-defined]
        return cls

    return decorator


def external(
    *,
    name: str,
    kind: StorageKind | str = "kv",
) -> Callable[[C], C]:
    """Declare an externally-provisioned resource.

    The decorated class must declare a `Backend` type-pin via its second
    generic parameter (`Store[T, Postgres]`, `BlobStore[S3]`, etc.).
    `name` indexes into `Environment.backends` at bind time — the runtime
    adapter reads the connection from there, and the deploy layer skips
    Pulumi provisioning for this resource.

    Args:
        name: Key into ``[env.<name>.backends]`` from `skaal.toml`.
        kind: The storage kind, mirroring `@storage`.

    Raises:
        SkaalConfigError: If the class is not type-pinned to a registered
            `Backend` subclass. External resources without a pin are not
            actionable — the binder cannot guess the wire protocol.
    """
    from skaal.errors import SkaalConfigError

    normalized_kind = _normalize_storage_kind(kind)

    def decorator(cls: C) -> C:
        pinned_token = _extract_backend_pin(cls)
        if pinned_token is None:
            raise SkaalConfigError(
                f"@external requires a Backend type-pin on {cls.__name__!r}; "
                "declare e.g. `class LegacyDb(Relational[Postgres])`."
            )
        _validate_storage_class(cls, kind=normalized_kind)
        overrides = ResourceOverrides(
            backend=pinned_token.name,
            external=True,
            external_name=name,
        )
        inferred = InferredResource(
            id=InferredResource.id_for(cls),
            kind=_STORAGE_KIND_TO_RESOURCE_KIND[normalized_kind],
            source=SourceLocation.from_object(cls),
            schema_=SchemaRef.from_class(cls),  # pyright: ignore[reportCallIssue]
            overrides=overrides,
        )
        cls.__skaal_inferred__ = inferred  # type: ignore[attr-defined]
        return cls

    return decorator


def function(
    *,
    retry: RetryPolicy | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    rate_limit: RateLimitPolicy | None = None,
    bulkhead: Bulkhead | None = None,
) -> Callable[[Callable[P, R]], FunctionRef[P, R]]:
    """Declare a Skaal compute function with optional resilience policies.

    Resilience policies (`retry`, `circuit_breaker`, `rate_limit`,
    `bulkhead`) are honoured by the runtime — see
    `skaal.runtime.middleware`. The decorator returns a `FunctionRef`
    carrying ``id``, ``overrides``, and ``__skaal_inferred__`` for
    runtime / deploy consumers; no per-decorator legacy dunder is
    written.

    The decorator factory's return type is
    ``Callable[[Callable[P, R]], FunctionRef[P, R]]`` — Pyright infers
    ``P`` and ``R`` from each decorated function, so call sites preserve
    the underlying signature (ADR 028 §6.13.3 "decorator preserves
    signatures").
    """

    def decorator(fn: Callable[P, R]) -> FunctionRef[P, R]:
        import contextlib

        overrides = ResourceOverrides(
            resilience=_resilience(
                retry=retry,
                circuit_breaker=circuit_breaker,
                rate_limit=rate_limit,
                bulkhead=bulkhead,
            ),
        )
        inferred = InferredResource(
            id=InferredResource.id_for(fn),
            kind=ResourceKind.FUNCTION,
            source=SourceLocation.from_object(fn),
            overrides=overrides,
        )
        with contextlib.suppress(AttributeError, TypeError):
            fn.__skaal_inferred__ = inferred  # type: ignore[attr-defined]
        return FunctionRef(fn, id=inferred.id, overrides=overrides, inferred=inferred)

    return decorator


def _resilience(
    *,
    retry: RetryPolicy | None,
    circuit_breaker: CircuitBreaker | None,
    rate_limit: RateLimitPolicy | None,
    bulkhead: Bulkhead | None,
) -> ResiliencePolicies | None:
    """Build a `ResiliencePolicies` from the four kwarg policies, or `None`.

    Collapsing the empty-envelope case to ``None`` keeps the `BoundPlan`
    fingerprint stable for resources that declare zero policies — the
    common case in examples and tests.
    """
    policies = ResiliencePolicies(
        retry=retry,
        circuit_breaker=circuit_breaker,
        rate_limit=rate_limit,
        bulkhead=bulkhead,
    )
    return None if policies.is_empty else policies
