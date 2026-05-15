"""Shared helpers used by the `run` / `plan` / `build` / `deploy` verbs.

All four verbs operate on a `BoundPlan`; the only differences are what
they do with it (serve, dump, render artefacts, push to Pulumi). The
`infer → load_environment → load_lock → bind` walk lives here so the
verb modules stay short and one obvious thing happens in each.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:
    from skaal.app import App
    from skaal.binding.model import BoundPlan


def load_app(target: str) -> Any:
    """Resolve a ``module:attribute`` reference to an `App` instance."""
    if ":" not in target:
        raise typer.BadParameter(
            f"`{target}` is not a `module:attribute` reference. "
            "Example: `examples.todo_api:app`."
        )
    module_path, attr = target.split(":", 1)
    module = importlib.import_module(module_path)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise typer.BadParameter(
            f"Module `{module_path}` has no attribute `{attr}`."
        ) from exc


def load_bound_plan(
    skaal_app: App,
    env_name: str,
    *,
    toml_path: Path = Path("skaal.toml"),
    lock_path: Path = Path("skaal.lock"),
) -> BoundPlan:
    """Walk ``infer → load env / lock → bind`` for ``skaal_app`` against ``env_name``."""
    bound, _env = load_bound_plan_with_env(
        skaal_app, env_name, toml_path=toml_path, lock_path=lock_path
    )
    return bound


def load_bound_plan_with_env(
    skaal_app: App,
    env_name: str,
    *,
    toml_path: Path = Path("skaal.toml"),
    lock_path: Path = Path("skaal.lock"),
) -> tuple[BoundPlan, Any]:
    """Same as `load_bound_plan` but also returns the resolved `Environment`.

    Used by the `build` / `deploy` verbs, which need to thread the env
    through to the deploy layer (`tags_for(...)` and the AWS synth
    functions both read it). Returning a tuple here avoids loading the
    TOML twice.
    """
    from skaal.binding import bind, load_environment, load_lock

    env = load_environment(env_name, path=toml_path)
    lock = load_lock(lock_path)
    plan = skaal_app.infer()
    return bind(plan, env, lock), env
