"""Shared helpers used by the `run` / `plan` / `build` / `deploy` verbs.

All four verbs operate on a `BoundPlan`; the only differences are what
they do with it (serve, dump, render artefacts, push to Pulumi). The
`infer → load_environment → load_lock → bind` walk lives here so the
verb modules stay short and one obvious thing happens in each.

The two value types in this module — `AppSpec` and `LoadedPlan` — keep
parsing and tuple-shapes out of the verb code:

- `AppSpec` parses ``module:attribute`` once; downstream consumers read
  `.reference`, `.module`, `.attribute`, and `.top_package` as typed
  attributes instead of re-splitting the string.
- `LoadedPlan` pairs the resolved `BoundPlan` with the `Environment` it
  was bound against, so verbs that need both (build, deploy, tags) get
  one well-named return rather than a tuple.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:
    from skaal.app import App
    from skaal.binding.model import BoundPlan, Environment


@dataclass(frozen=True)
class AppSpec:
    """Parsed ``module:attribute`` reference to a Skaal `App` instance.

    Parsing happens once at the boundary (the CLI verb, or the
    programmatic call site); downstream code reads the typed attributes
    rather than re-splitting the raw string.
    """

    module: str
    attribute: str

    @classmethod
    def parse(cls, raw: str) -> AppSpec:
        """Parse a ``module:attribute`` string.

        Raises:
            ValueError: If the input is not a ``module:attribute`` form.
        """
        if ":" not in raw:
            raise ValueError(
                f"`{raw}` is not a `module:attribute` reference. "
                "Example: `examples.todo_api:app`."
            )
        module, attribute = raw.split(":", 1)
        return cls(module=module, attribute=attribute)

    @classmethod
    def for_app(cls, app: App, *, attribute: str = "app") -> AppSpec:
        """Best-effort `AppSpec` for an already-instantiated `App`.

        Used by programmatic callers that pass an `App` instance directly
        and do not have a CLI-style reference string. The module is the
        live ``type(app).__module__`` (``__main__`` when the app was
        constructed in a script).
        """
        module = getattr(type(app), "__module__", "__main__") or "__main__"
        return cls(module=module, attribute=attribute)

    @property
    def reference(self) -> str:
        """The canonical ``module:attribute`` form."""
        return f"{self.module}:{self.attribute}"

    @property
    def top_package(self) -> str:
        """First dotted segment of `module`.

        This is the directory the Dockerfile copies into the build
        context and the value used for log-source identification. For
        ``examples.todo_api`` it is ``examples``; for ``my_service`` it
        is ``my_service``.
        """
        return self.module.partition(".")[0]


@dataclass(frozen=True)
class LoadedPlan:
    """The bound plan plus the environment it was bound against.

    The build and deploy verbs need both pieces (the plan for the
    resource walk, the environment for `tags_for(...)` and target
    dispatch). Returning a typed pair from the loader avoids the
    double-load that the previous tuple shape encouraged.
    """

    bound: BoundPlan
    env: Environment


def load_app_spec(target: str) -> AppSpec:
    """Parse ``target`` once and return the typed `AppSpec`."""
    return AppSpec.parse(target)


def load_app(target: str | AppSpec) -> Any:
    """Resolve a ``module:attribute`` reference to a live `App` instance.

    Accepts either a raw reference string or an already-parsed `AppSpec`
    so verb code that has the typed form does not pay the parse twice.
    """
    if isinstance(target, AppSpec):
        spec = target
    else:
        try:
            spec = AppSpec.parse(target)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    try:
        module = importlib.import_module(spec.module)
    except ImportError as exc:
        raise typer.BadParameter(f"Cannot import module `{spec.module}`: {exc}") from exc
    try:
        return getattr(module, spec.attribute)
    except AttributeError as exc:
        raise typer.BadParameter(
            f"Module `{spec.module}` has no attribute `{spec.attribute}`."
        ) from exc


def load_bound_plan(
    skaal_app: App,
    env_name: str,
    *,
    toml_path: Path = Path("skaal.toml"),
    lock_path: Path = Path("skaal.lock"),
) -> BoundPlan:
    """Walk ``infer → load env / lock → bind`` for ``skaal_app`` against ``env_name``."""
    return load_plan(
        skaal_app, env_name, toml_path=toml_path, lock_path=lock_path
    ).bound


def load_plan(
    skaal_app: App,
    env_name: str,
    *,
    toml_path: Path = Path("skaal.toml"),
    lock_path: Path = Path("skaal.lock"),
) -> LoadedPlan:
    """Walk ``infer → load env / lock → bind`` and return a typed `LoadedPlan`.

    Used by the `build` / `deploy` verbs that need both the bound plan
    and the environment. The `Environment` is constructed once and
    shared with the binding step, so callers see exactly the same view
    the binder did.
    """
    from skaal.binding import bind, load_environment, load_lock

    env = load_environment(env_name, path=toml_path)
    lock = load_lock(lock_path)
    plan = skaal_app.infer()
    return LoadedPlan(bound=bind(plan, env, lock), env=env)
