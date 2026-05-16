"""`skaal trace` — resolve a resource id or log line back to source."""

from __future__ import annotations

import typer
from rich.console import Console

from skaal.api import TraceHit, resolve_trace
from skaal.binding.model import BoundPlan
from skaal.cli._errors import cli_error_boundary
from skaal.cli._load import load_app, load_plan

app = typer.Typer(
    help="Resolve a resource id or log line back to the declaring source location.",
    context_settings={"allow_interspersed_args": True},
)


@app.callback(invoke_without_command=True)
@cli_error_boundary
def trace(
    needle: str = typer.Argument(
        ...,
        help="A resource id or any log line containing that resource id.",
    ),
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
    bound = load_plan(skaal_app, env_name).bound
    hit = _resolve(needle, bound)
    _render(hit, bound)


def _resolve(needle: str, bound: BoundPlan) -> TraceHit:
    """Resolve `needle` against the current bound plan."""
    try:
        return resolve_trace(needle, bound)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _render(hit: TraceHit, bound: BoundPlan) -> None:
    """Render `hit` to the terminal."""
    source = hit.resource.inferred.source
    console = Console()
    console.print(
        f"[bold]{bound.app}[/bold] / env=[cyan]{bound.environment}[/cyan]  "
        f"resource=[magenta]{hit.resource.inferred.id}[/magenta]"
    )
    console.print(f"matched  [dim]{hit.matched_text}[/dim]")
    console.print(f"source   [cyan]{source.file}:{source.line}[/cyan]")
    console.print(f"symbol   [green]{source.module}:{source.qualname}[/green]")
    console.print(
        "bound    "
        f"{hit.resource.inferred.kind.value} / {hit.resource.backend} / "
        f"{hit.resource.region or '-'}"
    )
