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
from skaal.cli._load import AppSpec, load_app, load_plan
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
    target: str = Argument(
        ...,
        help=(
            "Dotted module:attribute pointing at an `App` instance, e.g. `examples.todo_api:app`."
        ),
    ),
    env_name: str = Option(
        "prod",
        "--env",
        "-e",
        help="Environment name from `skaal.toml`.",
    ),
    out_dir: Path | None = Option(
        None,
        "--out",
        "-o",
        help=("Destination directory for rendered artefacts. Defaults to `./.skaal/build/<env>`."),
    ),
    yes: bool = Option(
        False,
        "--yes",
        "-y",
        help="Skip the interactive confirmation prompt and destroy immediately.",
    ),
    lock_path: Path = Option(
        Path("skaal.lock"),
        "--lock",
        help="Path to `skaal.lock` used during binding.",
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
    try:
        app_spec = AppSpec.parse(target)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    skaal_app = load_app(app_spec)
    loaded = load_plan(skaal_app, env_name, lock_path=lock_path)

    written = build_artefacts(loaded.bound, loaded.env, app_spec, out_dir=out_dir, dev=dev)
    console = Console()
    console.print(f"Rendered artefacts for [cyan]{env_name}[/cyan] → {written}")

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
