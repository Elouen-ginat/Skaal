"""Python equivalents for the surviving CLI verbs."""

from __future__ import annotations

from pathlib import Path
from typing import TypeAlias

from skaal.app import App
from skaal.binding import LockFile
from skaal.cli._load import load_app, load_plan

from ._commands import (
    BuildResult,
    DeployResult,
    DoctorReport,
    StubResult,
    build,
    deploy,
    doctor,
    init,
    run,
    stubs,
)
from ._plan import PlanChange, PlanDiff, diff_bound_plans, diff_plan, render_plan_diff_markdown
from ._resource_map import ResourceMap, ResourceMapEntry
from ._trace import SourceMatch, resolve_trace
from ._where import Location, resolve_where

AppRef: TypeAlias = App | str

__all__ = [
    "AppRef",
    "BuildResult",
    "DeployResult",
    "DoctorReport",
    "Location",
    "PlanChange",
    "PlanDiff",
    "ResourceMap",
    "ResourceMapEntry",
    "SourceMatch",
    "StubResult",
    "build",
    "deploy",
    "diff_bound_plans",
    "diff_plan",
    "doctor",
    "find_source",
    "init",
    "locate",
    "plan",
    "render_plan_diff_markdown",
    "resolve_trace",
    "resources",
    "run",
    "stubs",
]


def plan(
    target: AppRef,
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
        _resolve_app_ref(target),
        env_name,
        toml_path=toml_path,
        lock_path=lock_path,
    )
    return diff_plan(loaded.bound, LockFile.load(lock_path))


def resources(
    target: AppRef,
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
        _resolve_app_ref(target),
        env_name,
        toml_path=toml_path,
        lock_path=lock_path,
    )
    resource_map = ResourceMap.for_bound_plan(loaded.bound)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(resource_map.to_json(), encoding="utf-8")
    return resource_map


def find_source(
    needle: str,
    target: AppRef,
    *,
    env_name: str = "local",
    toml_path: Path = Path("skaal.toml"),
    lock_path: Path = Path("skaal.lock"),
) -> SourceMatch:
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
        _resolve_app_ref(target),
        env_name,
        toml_path=toml_path,
        lock_path=lock_path,
    )
    return resolve_trace(needle, loaded.bound)


def locate(
    resource_id: str,
    target: AppRef,
    *,
    env_name: str = "prod",
    toml_path: Path = Path("skaal.toml"),
    lock_path: Path = Path("skaal.lock"),
) -> Location:
    """Resolve a resource id to its deployed cloud-console URL.

    Args:
        resource_id: Bound resource id to locate.
        target: `module:attribute` reference or live `App` instance.
        env_name: Environment name from `skaal.toml`.
        toml_path: Settings file path.
        lock_path: Lock file path.

    Returns:
        The resolved deployed-resource location.
    """
    loaded = load_plan(
        _resolve_app_ref(target),
        env_name,
        toml_path=toml_path,
        lock_path=lock_path,
    )
    return resolve_where(resource_id, loaded.bound, loaded.env)


def _resolve_app_ref(target: AppRef) -> App:
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
