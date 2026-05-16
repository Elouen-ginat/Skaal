"""Skaal exception hierarchy.

The solver / catalog exception classes (`SkaalSolverError`,
`UnsatisfiableConstraints`, `CatalogError`) have been removed per ADR 028
along with the constraint solver itself.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class SkaalError(Exception):
    """Base class for every Skaal-originating exception."""

    exit_code: int = 1


# ── Backend / storage-layer errors ────────────────────────────────────────────


class SkaalBackendError(SkaalError):
    """A storage backend failed an operation."""


class SkaalConflict(SkaalBackendError):
    """An optimistic-concurrency / compare-and-swap update lost the race."""


class SkaalUnavailable(SkaalBackendError):
    """Transient, retriable failure (network blip, pool exhausted, 5xx)."""


# ── Deploy errors ─────────────────────────────────────────────────────────────


class SkaalDeployError(SkaalError):
    """Deployment packaging, orchestration, or rollout failed."""


class SkaalHookError(SkaalDeployError):
    """A pre-deploy or post-deploy hook failed."""


class PlanError(SkaalError):
    """Plan generation failed."""


class BuildError(SkaalError):
    """Artifact generation failed."""


# ── Config errors ────────────────────────────────────────────────────────────


class SkaalConfigError(SkaalError):
    """Configuration (settings, pyproject) is invalid or unreadable."""


class TypePinViolation(SkaalConfigError):
    """An env override or lock entry tried to repoint a type-pinned resource.

    Type-pinning a class (``Relational[BigQuery]``) is a commitment —
    the binder refuses any override that names a different backend for the
    same resource, raising at config-load time per ADR 028 §6.5.3.
    """

    def __init__(self, resource_id: str, declared: str, requested: str) -> None:
        self.resource_id = resource_id
        self.declared = declared
        self.requested = requested
        super().__init__(
            f"Resource {resource_id!r} is type-pinned to backend {declared!r}; "
            f"override names {requested!r}. Pinning is a commitment — either "
            f"drop the second generic parameter at the declaration site or "
            f"remove the conflicting override."
        )


class BackendKindMismatch(SkaalConfigError):
    """The chosen backend cannot host the resource's required kind."""

    def __init__(self, resource_id: str, backend: str, required_kind: str) -> None:
        self.resource_id = resource_id
        self.backend = backend
        self.required_kind = required_kind
        super().__init__(
            f"Backend {backend!r} does not support kind {required_kind!r} "
            f"required by {resource_id!r}."
        )


class BackendNotAvailableForTarget(SkaalConfigError):
    """The chosen backend is not deployable on the active environment's target."""

    def __init__(self, backend: str, target: str) -> None:
        self.backend = backend
        self.target = target
        super().__init__(f"Backend {backend!r} is not available on target {target!r}.")


class UnknownBackendError(SkaalConfigError):
    """A backend name was used that the registry does not know."""

    def __init__(self, name: str, valid: tuple[str, ...]) -> None:
        self.name = name
        self.valid = valid
        super().__init__(
            f"Unknown backend {name!r}. Registered backends: "
            f"{', '.join(valid) if valid else '(none)'}."
        )


class SecretMissingError(SkaalConfigError):
    """A required secret could not be resolved at runtime warmup."""

    def __init__(self, name: str, provider: str, *, detail: str | None = None) -> None:
        self.name = name
        self.provider = provider
        message = f"Required secret {name!r} not found via provider {provider!r}"
        if detail:
            message = f"{message} ({detail})"
        super().__init__(message)


# ── Optional-extra import wrapping ────────────────────────────────────────────


class MissingExtraError(SkaalError):
    """An optional dependency group is not installed."""


# ── Runtime errors ───────────────────────────────────────────────────────────


class RuntimeAdapterMissing(SkaalError):
    """The local runtime has no adapter wired for a resource kind.

    Raised when the dispatch table in `skaal.runtime.dispatch` is asked
    for a kind that has not been hooked up yet. Phase 4 ships first-class
    adapters for the kinds the local defaults table emits; remaining
    kinds raise this until their adapter lands.
    """

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(
            f"No local runtime adapter is wired for resource kind {kind!r}. "
            "This kind will be supported in a follow-up Phase 4 PR."
        )


class RuntimeResourceUnresolved(SkaalError):
    """A `BoundResource.id` could not be resolved back to a live Python object.

    The runtime walks the user's `App` graph to find the live `Store`
    subclass / `@app.function` callable / channel instance behind every
    `BoundResource`. This is raised when the addressing scheme falls out
    of sync — typically because the user constructed a `BoundPlan` from
    a different `App` than the one passed to `LocalRuntime`.
    """

    def __init__(self, resource_id: str) -> None:
        self.resource_id = resource_id
        super().__init__(
            f"Cannot resolve resource {resource_id!r} to a live object on the App. "
            "The BoundPlan and App must come from the same inference run."
        )


def require_extra(
    extra: str,
    modules: Iterable[str],
    *,
    feature: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator that turns a missing optional dependency into `MissingExtraError`."""
    feature_name = feature or extra
    module_list = list(modules)

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for mod in module_list:
                try:
                    __import__(mod)
                except ImportError as exc:
                    raise MissingExtraError(
                        f"{feature_name} requires the {extra!r} extra. "
                        f"Install it with `pip install 'skaal[{extra}]'`."
                    ) from exc
            return func(*args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "BuildError",
    "MissingExtraError",
    "PlanError",
    "RuntimeAdapterMissing",
    "RuntimeResourceUnresolved",
    "SecretMissingError",
    "SkaalBackendError",
    "SkaalConfigError",
    "SkaalConflict",
    "SkaalDeployError",
    "SkaalError",
    "SkaalHookError",
    "SkaalUnavailable",
    "require_extra",
]
