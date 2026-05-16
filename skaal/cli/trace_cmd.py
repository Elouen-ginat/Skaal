"""`skaal trace` — resolve a resource id or log line back to source."""

from __future__ import annotations

from dataclasses import dataclass

import typer
from rich.console import Console

from skaal.binding.model import BoundPlan, BoundResource
from skaal.cli._errors import cli_error_boundary
from skaal.cli._load import load_app, load_plan

app = typer.Typer(
    help="Resolve a resource id or log line back to the declaring source location.",
    context_settings={"allow_interspersed_args": True},
)


@dataclass(frozen=True)
class TraceHit:
    """One resolved trace result."""

    resource: BoundResource
    matched_text: str


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
    resources = bound.resources
    best_match: BoundResource | None = None
    for resource in resources:
        if needle == resource.inferred.id:
            return TraceHit(resource=resource, matched_text=resource.inferred.id)

    matches = [resource for resource in resources if resource.inferred.id in needle]
    if matches:
        best_match = max(matches, key=lambda resource: len(resource.inferred.id))
    if best_match is not None:
        return TraceHit(resource=best_match, matched_text=best_match.inferred.id)

    known_ids = ", ".join(
        [resource.inferred.id for resource in resources[:5]]
        + (["..."] if len(resources) > 5 else [])
    )
    raise typer.BadParameter(
        "Could not resolve that input to a known resource id. "
        f"Expected one of: {known_ids or '(no resources)'}."
    )


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
