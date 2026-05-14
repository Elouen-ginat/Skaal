"""`skaal plan` — render the `BoundPlan` for the requested environment.

Phase 4 ships a human-readable dump of the bound plan; the diff form
(against `LockFile` or live state) lands in Phase 6 alongside the
`map` / `where` / `trace` work (ADR 028 §6.7, ADR 032 §4.8).
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from skaal.binding.model import BoundPlan
from skaal.cli._errors import cli_error_boundary
from skaal.cli._load import load_app, load_bound_plan

app = typer.Typer(
    help="Render the bound plan for the requested environment.",
    context_settings={"allow_interspersed_args": True},
)


@app.callback(invoke_without_command=True)
@cli_error_boundary
def plan(
    target: str = typer.Argument(
        ...,
        help=(
            "Dotted module:attribute pointing at an `App` instance, e.g. "
            "`examples.todo_api:app`."
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
    bound = load_bound_plan(skaal_app, env_name)
    _render(bound)


def _render(bound: BoundPlan) -> None:
    console = Console()
    console.print(
        f"[bold]{bound.app}[/bold] / env=[cyan]{bound.environment}[/cyan]  "
        f"app={bound.app_fingerprint or '-'}  bound={bound.bound_fingerprint or '-'}"
    )

    table = Table(show_header=True, header_style="bold")
    table.add_column("Resource")
    table.add_column("Kind")
    table.add_column("Backend")
    table.add_column("Region")
    table.add_column("Pinned")
    table.add_column("External")

    for res in bound.resources:
        table.add_row(
            res.inferred.id,
            res.inferred.kind.value,
            res.backend,
            res.region or "-",
            "yes" if res.pinned else "-",
            "yes" if res.external else "-",
        )

    console.print(table)
    if not bound.resources:
        console.print("[dim]No resources discovered.[/dim]")
