"""`skaal stubs` — emit a typed `.pyi` package describing a Skaal app.

ADR 028 §6.6.1: the one case where codegen is justified in the framework
is a cross-process stub package, so a consuming project can get LSP
completion for another service's primitives without importing its
runtime. Same-process callers do not run this command.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from skaal.cli._errors import cli_error_boundary
from skaal.stubs.emit import StubEmitError, discover_app, emit_stubs

app = typer.Typer(
    help="Emit a typed `.pyi` package describing a Skaal app (ADR 028 §6.6.1).",
    context_settings={"allow_interspersed_args": True},
)


@app.callback(invoke_without_command=True)
@cli_error_boundary
def stubs(
    source: str = typer.Option(
        ...,
        "--from",
        help=(
            "Path to a Skaal app package, or a `module:attribute` reference "
            "(e.g. `services.billing:app`)."
        ),
    ),
    out_dir: Path = typer.Option(
        ...,
        "--to",
        help="Destination directory for the emitted stub package.",
    ),
    package_name: str | None = typer.Option(
        None,
        "--as",
        help=(
            "Python package name consumers will import. Defaults to the "
            "destination directory's base name."
        ),
    ),
) -> None:
    """Emit a stub package for the app reachable from ``--from``."""
    console = Console()
    pkg = package_name or out_dir.resolve().name
    try:
        skaal_app = discover_app(Path(source))
        written = emit_stubs(app=skaal_app, out_dir=out_dir, package_name=pkg)
    except StubEmitError as exc:
        raise typer.BadParameter(str(exc)) from exc

    resource_count = len(skaal_app.infer().resources)
    console.print(
        f"[green]Wrote stub package[/green] [bold]{pkg}[/bold] -> [cyan]{written}[/cyan]"
        f" ({resource_count} resource{'s' if resource_count != 1 else ''})"
    )
