"""`skaal deploy` — render artefacts and drive Pulumi via the Automation API.

The verb walks `infer → bind`, renders the build tree via
`build_artefacts(...)`, then invokes `pulumi.automation` to spin up (or
update) a stack whose program is `pulumi_program_for(bound, env, build_dir)`.

On success the lock file is updated with the bindings the stack used so
follow-up runs of `skaal plan` short-circuit when nothing has changed.
The actual lock-write step is gated on whether the binder pinned any
new resources during this run.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from skaal.binding.model import Environment, LockEntry, LockFile, Plan
from skaal.cli._errors import cli_error_boundary
from skaal.cli._load import AppSpec, load_app, load_plan
from skaal.cli._params import Argument, Option
from skaal.deploy import (
    PulumiProgram,
    build_artefacts,
    get_target,
    pulumi_program_for,
)
from skaal.errors import MissingExtraError, SkaalDeployError

app = typer.Typer(
    help="Provision infrastructure via Pulumi.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def deploy(
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
    preview: bool = Option(
        False,
        "--preview",
        help="Run `pulumi preview` instead of `pulumi up`.",
    ),
    yes: bool = Option(
        False,
        "--yes",
        "-y",
        help="Skip the interactive confirmation prompt and apply immediately.",
    ),
    lock_path: Path = Option(
        Path("skaal.lock"),
        "--lock",
        help="Path to `skaal.lock` (created on first deploy).",
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
    _run_pulumi(
        bound=loaded.bound,
        env=loaded.env,
        program=program,
        preview=preview,
        yes=yes,
        console=console,
    )

    _write_lock_pins(loaded.bound, loaded.env, lock_path=lock_path)
    console.print(f"[green]✓[/green] {'preview' if preview else 'deploy'} complete.")


def _run_pulumi(
    *,
    bound: Plan,
    env: Environment,
    program: PulumiProgram,
    preview: bool,
    yes: bool,
    console: Console,
) -> None:
    """Invoke the Pulumi Automation API against `program`.

    Imports `pulumi.automation` lazily so the rest of the CLI does not
    pay the import cost. Stack naming and stack-config wiring delegate
    to the registered `DeployTarget` so a new cloud target plugs in
    without editing this file.
    """
    try:
        from pulumi import automation as auto
    except ImportError as exc:
        raise MissingExtraError(
            "`skaal deploy` requires the Pulumi SDKs. Install them with "
            "`pip install 'skaal[deploy,aws]'`."
        ) from exc

    # Importing the target package registers the target; the program
    # callable would do this on invocation, but we need the target
    # registered here too for stack-name / stack-config wiring.
    __import__(f"skaal.deploy.{env.target.value}")
    target = get_target(env.target)

    project_name = bound.app or "skaal"
    stack_name = target.stack_name(bound, env)
    console.print(f"Pulumi stack [bold]{stack_name}[/bold] (project=[cyan]{project_name}[/cyan])")

    stack = auto.create_or_select_stack(
        stack_name=stack_name,
        project_name=project_name,
        program=program,
    )
    for key, value in target.stack_config(env).items():
        stack.set_config(key, auto.ConfigValue(value=value))

    try:
        if preview:
            stack.preview(on_output=console.print)
        else:
            if not yes and not typer.confirm(
                f"Apply {stack_name!r} to target {env.target.value!r}?",
                default=False,
            ):
                raise typer.Abort()
            result = stack.up(on_output=console.print)
            _print_stack_outputs(result.outputs, console)
    except auto.CommandError as exc:  # pragma: no cover - network/integration path
        raise SkaalDeployError(f"Pulumi {('preview' if preview else 'up')} failed: {exc}") from exc


def _print_stack_outputs(outputs: Mapping[str, Any] | None, console: Console) -> None:
    """Render exported stack outputs in a stable, Skaal-owned format."""
    if not outputs:
        return
    rendered: list[tuple[str, str]] = []
    for key in sorted(outputs):
        raw = outputs[key]
        value = getattr(raw, "value", raw)
        if value is None:
            continue
        rendered.append((key, str(value)))
    if not rendered:
        return

    console.print("Stack outputs:")
    for key, value in rendered:
        console.print(f"  [cyan]{key}[/cyan] = {value}")


def _write_lock_pins(bound: Plan, env: Environment, *, lock_path: Path) -> None:
    """Pin every non-external bound resource into `skaal.lock`.

    First-deploy runs convert the binder's defaults / overrides into
    explicit `LockEntry` rows so subsequent `skaal plan` runs short-circuit
    when nothing has changed. Already-locked entries are kept as-is.
    """
    existing = LockFile.load(lock_path)
    new_entries = dict(existing.entries)
    now = datetime.now(UTC)
    for resource in bound.resources:
        if resource.external:
            continue
        key = (env.name, resource.inferred.id)
        if key in new_entries:
            continue
        new_entries[key] = LockEntry(
            backend=resource.backend,
            region=resource.region,
            pinned_at=now,
            pinned_by="skaal-deploy",
            fingerprint=bound.bound_fingerprint or None,
        )

    if new_entries != existing.entries:
        updated = LockFile(version=existing.version, entries=new_entries)
        updated.save(lock_path)
