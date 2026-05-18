"""Shared helpers used by the `run` / `plan` / `build` / `deploy` verbs.

All four verbs operate on a `BoundPlan`; the only differences are what
they do with it (serve, dump, render artefacts, push to Pulumi). The
`blueprint → Environment.load → LockFile.load → plan` walk lives here so the
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

from skaal.settings import get_settings, load_settings

if TYPE_CHECKING:
    from skaal.app import App
    from skaal.binding.model import Environment, Plan


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
                f"`{raw}` is not a `module:attribute` reference. Example: `examples.todo_api:app`."
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

    bound: Plan
    env: Environment


def load_app_spec(target: str) -> AppSpec:
    """Parse ``target`` once and return the typed `AppSpec`."""
    return resolve_app_spec(target)


def resolve_app_target(target: str | None) -> str:
    """Return an explicit or configured `module:attribute` app target."""
    if target is not None:
        return target
    configured = get_settings().app
    if configured is not None:
        return configured
    raise typer.BadParameter(
        "Missing app target. Pass `module:attribute` explicitly or set "
        "`[tool.skaal].app` / `SKAAL_APP`."
    )


def resolve_app_spec(target: str | AppSpec | None) -> AppSpec:
    """Resolve an explicit or configured app target into `AppSpec`."""
    if isinstance(target, AppSpec):
        return target
    raw = resolve_app_target(target)
    return AppSpec.parse(raw)


def resolve_env_name(
    env_name: str | None,
    *,
    toml_path: Path | None = None,
    fallback: str,
) -> str:
    """Resolve an environment name from CLI input, config, or a fallback."""
    if env_name is not None:
        return env_name
    settings = load_settings(toml_path=toml_path or get_settings().toml)
    return settings.default_environment or fallback


def resolve_toml_path(path: Path | None = None) -> Path:
    """Return the explicit or configured `skaal.toml` path."""
    return path or get_settings().toml


def resolve_lock_path(path: Path | None = None) -> Path:
    """Return the explicit or configured `skaal.lock` path."""
    return path or get_settings().lock


def resolve_build_out_dir(out_dir: Path | None, env_name: str) -> Path:
    """Return the explicit or configured build output directory for `env_name`."""
    return out_dir or get_settings().out / env_name


def load_app(target: str | AppSpec | None) -> Any:
    """Resolve a ``module:attribute`` reference to a live `App` instance.

    Accepts either a raw reference string or an already-parsed `AppSpec`
    so verb code that has the typed form does not pay the parse twice.
    """
    try:
        spec = resolve_app_spec(target)
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
    env_name: str | None,
    *,
    toml_path: Path | None = None,
    lock_path: Path | None = None,
    fallback_env: str = "local",
) -> Plan:
    """Walk ``blueprint → Environment.load → LockFile.load → plan`` for an app."""
    return load_plan(
        skaal_app,
        env_name,
        toml_path=toml_path,
        lock_path=lock_path,
        fallback_env=fallback_env,
    ).bound


def load_plan(
    skaal_app: App,
    env_name: str | None,
    *,
    toml_path: Path | None = None,
    lock_path: Path | None = None,
    fallback_env: str = "local",
) -> LoadedPlan:
    """Walk ``blueprint → Environment.load → LockFile.load → plan`` once.

    Used by the `build` / `deploy` verbs that need both the bound plan
    and the environment. The `Environment` is constructed once and
    shared with the binding step, so callers see exactly the same view
    the binder did.
    """
    from skaal.binding import Environment, LockFile

    resolved_toml = resolve_toml_path(toml_path)
    resolved_lock = resolve_lock_path(lock_path)
    resolved_env = resolve_env_name(env_name, toml_path=resolved_toml, fallback=fallback_env)
    env = Environment.load(resolved_env, path=resolved_toml)
    lock = LockFile.load(resolved_lock)
    return LoadedPlan(bound=skaal_app.plan(env, lock=lock), env=env)
