"""Python equivalents for the surviving CLI verbs."""

from __future__ import annotations

from pathlib import Path
from typing import TypeAlias

from skaal.app import App
from skaal.binding import load_lock
from skaal.cli._load import load_app, load_plan
from skaal.plan_diff import PlanDiff, diff_plan
from skaal.resource_map import ResourceMap
from skaal.traceability import TraceHit, resolve_trace

AppTarget: TypeAlias = App | str

__all__ = ["AppTarget", "PlanDiff", "ResourceMap", "TraceHit", "map", "plan", "trace"]


def plan(
    target: AppTarget,
    *,
    env_name: str = "local",
    toml_path: Path = Path("skaal.toml"),
    lock_path: Path = Path("skaal.lock"),
) -> PlanDiff:
    """Return the lock diff for `target`.

    Args:
        target: `module:attribute` reference or live `App` instance.
        env_name: Environment name from `skaal.toml`.
        toml_path: Settings file path.
        lock_path: Lock file path.

    Returns:
        The diff between the current bound plan and the lock file.
    """
    loaded = load_plan(
        _coerce_app(target),
        env_name,
        toml_path=toml_path,
        lock_path=lock_path,
    )
    return diff_plan(loaded.bound, load_lock(lock_path))


def map(
    target: AppTarget,
    *,
    env_name: str = "local",
    toml_path: Path = Path("skaal.toml"),
    lock_path: Path = Path("skaal.lock"),
    out_path: Path | None = None,
) -> ResourceMap:
    """Return and optionally persist the source-to-resource map for `target`.

    Args:
        target: `module:attribute` reference or live `App` instance.
        env_name: Environment name from `skaal.toml`.
        toml_path: Settings file path.
        lock_path: Lock file path.
        out_path: Optional path for the emitted JSON sidecar.

    Returns:
        The validated resource map for the bound plan.
    """
    loaded = load_plan(
        _coerce_app(target),
        env_name,
        toml_path=toml_path,
        lock_path=lock_path,
    )
    resource_map = ResourceMap.for_bound_plan(loaded.bound)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(resource_map.to_json(), encoding="utf-8")
    return resource_map


def trace(
    needle: str,
    target: AppTarget,
    *,
    env_name: str = "local",
    toml_path: Path = Path("skaal.toml"),
    lock_path: Path = Path("skaal.lock"),
) -> TraceHit:
    """Resolve a resource id or log line back to a source location.

    Args:
        needle: Resource id or log line containing a resource id.
        target: `module:attribute` reference or live `App` instance.
        env_name: Environment name from `skaal.toml`.
        toml_path: Settings file path.
        lock_path: Lock file path.

    Returns:
        The resolved trace hit.
    """
    loaded = load_plan(
        _coerce_app(target),
        env_name,
        toml_path=toml_path,
        lock_path=lock_path,
    )
    return resolve_trace(needle, loaded.bound)


def _coerce_app(target: AppTarget) -> App:
    """Resolve `target` to a live `App` instance.

    Args:
        target: `module:attribute` reference or live `App` instance.

    Returns:
        The resolved `App`.

    Raises:
        TypeError: If the resolved object is not a Skaal `App`.
    """
    if isinstance(target, str):
        resolved = load_app(target)
        if not isinstance(resolved, App):
            msg = f"`{target}` did not resolve to a Skaal `App` instance."
            raise TypeError(msg)
        return resolved
    return target
