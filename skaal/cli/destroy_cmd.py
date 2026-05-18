"""`skaal destroy` — tear down deployed infrastructure via the Automation API.

The verb mirrors `skaal deploy`: it walks `infer → bind`, renders the build
tree, then selects the existing Pulumi stack for the target environment and
destroys it. The stack itself is removed after the destroy completes.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console

from skaal.binding.model import Environment, Plan
from skaal.cli._errors import cli_error_boundary
from skaal.cli._load import (
    load_app,
    load_plan,
    resolve_app_spec,
    resolve_build_out_dir,
    resolve_lock_path,
)
from skaal.cli._params import Argument, Option
from skaal.cli._pulumi import apply_pulumi_defaults
from skaal.deploy import PulumiProgram, build_artefacts, get_target, pulumi_program_for
from skaal.errors import MissingExtraError, SkaalDeployError

app = typer.Typer(
    help="Destroy infrastructure provisioned by `skaal deploy`.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def destroy(
    target: str | None = Argument(
        None,
        help=(
            "Dotted module:attribute pointing at an `App` instance. When omitted, "
            "falls back to `[tool.skaal].app` / `SKAAL_APP`."
        ),
    ),
    env_name: str | None = Option(
        None,
        "--env",
        "-e",
        help=(
            "Environment name from `skaal.toml`. When omitted, falls back to "
            "`[tool.skaal].default_environment` / `SKAAL_DEFAULT_ENVIRONMENT`, then `prod`."
        ),
    ),
    out_dir: Path | None = Option(
        None,
        "--out",
        "-o",
        help=(
            "Destination directory for rendered artefacts. Defaults to "
            "`[tool.skaal].out/<env>` or `./.skaal/build/<env>`."
        ),
    ),
    yes: bool = Option(
        False,
        "--yes",
        "-y",
        help="Skip the interactive confirmation prompt and destroy immediately.",
    ),
    lock_path: Path | None = Option(
        None,
        "--lock",
        help="Path to `skaal.lock` used during binding (defaults to config).",
    ),
    dev: bool = Option(
        False,
        "--dev",
        help=(
            "Ship the local Skaal checkout inside each Lambda image instead of "
            "installing `skaal[...]` from PyPI. Use during the 0.4.0 alpha while "
            "the package is not yet published."
        ),
    ),
) -> None:
    app_spec = resolve_app_spec(target)
    skaal_app = load_app(app_spec)
    resolved_lock_path = resolve_lock_path(lock_path)
    loaded = load_plan(
        skaal_app,
        env_name,
        lock_path=resolved_lock_path,
        fallback_env="prod",
    )
    resolved_out_dir = resolve_build_out_dir(out_dir, loaded.env.name)

    written = build_artefacts(
        loaded.bound,
        loaded.env,
        app_spec,
        out_dir=resolved_out_dir,
        dev=dev,
    )
    console = Console()
    console.print(f"Rendered artefacts for [cyan]{loaded.env.name}[/cyan] → {written}")

    program = pulumi_program_for(loaded.bound, loaded.env, written)
    _destroy_pulumi(
        bound=loaded.bound,
        env=loaded.env,
        program=program,
        yes=yes,
        console=console,
    )

    console.print("[green]✓[/green] destroy complete.")


def _destroy_pulumi(
    *,
    bound: Plan,
    env: Environment,
    program: PulumiProgram,
    yes: bool,
    console: Console,
) -> None:
    """Invoke the Pulumi Automation API to destroy and remove an existing stack."""
    apply_pulumi_defaults(console)
    try:
        from pulumi import automation as auto
    except ImportError as exc:
        raise MissingExtraError(
            "`skaal destroy` requires the Pulumi SDKs. Install them with "
            "`pip install 'skaal[deploy,aws]'`."
        ) from exc

    __import__(f"skaal.deploy.{env.target.value}")
    target = get_target(env.target)

    project_name = bound.app or "skaal"
    stack_name = target.stack_name(bound, env)
    console.print(f"Pulumi stack [bold]{stack_name}[/bold] (project=[cyan]{project_name}[/cyan])")

    try:
        stack = auto.select_stack(
            stack_name=stack_name,
            project_name=project_name,
            program=program,
        )
    except Exception as exc:  # pragma: no cover - network/integration path
        raise SkaalDeployError(
            f"Could not open Pulumi stack {stack_name!r} for project {project_name!r}: {exc}"
        ) from exc

    for key, value in target.stack_config(env).items():
        stack.set_config(key, auto.ConfigValue(value=value))

    try:
        if not yes and not typer.confirm(
            f"Destroy {stack_name!r} on target {env.target.value!r}?",
            default=False,
        ):
            raise typer.Abort()
        stack.destroy(on_output=console.print, remove=True, program=program)
    except auto.CommandError as exc:  # pragma: no cover - network/integration path
        raise SkaalDeployError(f"Pulumi destroy failed: {exc}") from exc
