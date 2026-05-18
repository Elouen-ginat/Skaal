"""`skaal where` — resolve a deployed resource to its cloud-console URL."""

from __future__ import annotations

import typer
from rich.console import Console

from skaal.api import Location
from skaal.api import locate as api_where
from skaal.cli._errors import cli_error_boundary
from skaal.cli._load import resolve_app_target, resolve_env_name
from skaal.cli._params import Argument, Option

app = typer.Typer(
    help="Resolve a deployed resource id to its cloud-console URL.",
    context_settings={"allow_interspersed_args": True},
)


@app.callback(invoke_without_command=True)
@cli_error_boundary
def where(
    resource_id: str = Argument(
        ...,
        help="Bound resource id to locate, e.g. `examples.todo_api:Comments`.",
    ),
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
) -> None:
    hit = api_where(
        resource_id,
        resolve_app_target(target),
        env_name=resolve_env_name(env_name, fallback="prod"),
    )
    _render(hit)


def _render(hit: Location) -> None:
    """Render `hit` to the terminal."""
    console = Console()
    source = hit.resource.inferred.source
    app_name = source.top_package or source.module or hit.resource.inferred.id
    console.print(f"[bold]{app_name}[/bold] / stack=[cyan]{hit.stack_name}[/cyan]")
    console.print(f"resource [magenta]{hit.resource.inferred.id}[/magenta]")
    console.print(f"type     [green]{hit.provider_type}[/green]")
    if hit.physical_id:
        console.print(f"id       [cyan]{hit.physical_id}[/cyan]")
    console.print(f"url      [link={hit.console_url}]{hit.console_url}[/link]")


__all__ = ["app"]
