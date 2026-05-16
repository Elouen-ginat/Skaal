"""`skaal where` — resolve a deployed resource to its cloud-console URL."""

from __future__ import annotations

import typer
from rich.console import Console

from skaal.api import WhereHit
from skaal.api import where as api_where
from skaal.cli._errors import cli_error_boundary

app = typer.Typer(
    help="Resolve a deployed resource id to its cloud-console URL.",
    context_settings={"allow_interspersed_args": True},
)


@app.callback(invoke_without_command=True)
@cli_error_boundary
def where(
    resource_id: str = typer.Argument(
        ...,
        help="Bound resource id to locate, e.g. `examples.todo_api:Comments`.",
    ),
    target: str = typer.Argument(
        ...,
        help=(
            "Dotted module:attribute pointing at an `App` instance, e.g. `examples.todo_api:app`."
        ),
    ),
    env_name: str = typer.Option(
        "prod",
        "--env",
        "-e",
        help="Environment name from `skaal.toml`.",
    ),
) -> None:
    hit = api_where(resource_id, target, env_name=env_name)
    _render(hit)


def _render(hit: WhereHit) -> None:
    """Render `hit` to the terminal."""
    console = Console()
    console.print(
        f"[bold]{hit.resource.inferred.source.top_package}[/bold] "
        f"/ stack=[cyan]{hit.stack_name}[/cyan]"
    )
    console.print(f"resource [magenta]{hit.resource.inferred.id}[/magenta]")
    console.print(f"type     [green]{hit.provider_type}[/green]")
    if hit.physical_id:
        console.print(f"id       [cyan]{hit.physical_id}[/cyan]")
    console.print(f"url      [link={hit.console_url}]{hit.console_url}[/link]")


__all__ = ["app"]
