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
