"""`skaal plan` — render the environment diff implied by the current app.

Phase 6 starts by diffing the current `BoundPlan` against `skaal.lock` for
the requested environment. Live deployed-state reconciliation, `skaal map`,
and `where` / `trace` land in follow-ups.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from skaal.api import PlanDiff, diff_plan
from skaal.binding import load_lock
from skaal.cli._errors import cli_error_boundary
from skaal.cli._load import load_app, load_plan

app = typer.Typer(
    help="Render the diff between the current app and `skaal.lock`.",
    context_settings={"allow_interspersed_args": True},
)
@app.callback(invoke_without_command=True)
@cli_error_boundary
def plan(
    target: str = typer.Argument(
        ...,
        help=(
            "Dotted module:attribute pointing at an `App` instance, e.g. `examples.todo_api:app`."
        ),
    ),
    env_name: str = typer.Option(
        "local",
        "--env",
        "-e",
        help="Environment name from `skaal.toml` (defaults to `local`).",
    ),
) -> None:
    skaal_app = load_app(target)
    loaded_plan = load_plan(skaal_app, env_name)
    lock = load_lock(Path("skaal.lock"))
    _render(diff_plan(loaded_plan.bound, lock))


def _render(diff: PlanDiff) -> None:
    console = Console()
    console.print(
        f"[bold]{diff.bound.app}[/bold] / env=[cyan]{diff.bound.environment}[/cyan]  "
        f"app={diff.bound.app_fingerprint or '-'}  "
        f"current={diff.bound.bound_fingerprint or '-'}  "
        f"deployed={diff.deployed_fingerprint or '-'}"
    )

    if not diff.bound.resources:
        console.print("[dim]No resources discovered.[/dim]")
        return

    if not diff.changes:
        console.print("[green]No changes.[/green] `skaal.lock` already matches this plan.")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Action")
    table.add_column("Resource")
    table.add_column("Kind")
    table.add_column("Backend")
    table.add_column("Region")
    table.add_column("Details")

    for change in diff.changes:
        table.add_row(
            change.action,
            change.resource_id,
            change.kind,
            change.backend,
            change.region or "-",
            change.details,
        )

    console.print(table)
