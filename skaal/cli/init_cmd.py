"""`skaal init` — scaffold a new Skaal project.

The scaffolder is rewritten in Phase 5 of ADR 028 to emit a project that
exercises the new typed-primitive surface and writes a `skaal.toml`
instead of the legacy `catalogs/*.toml` overlay. Until then this command
surfaces a clear error rather than scaffolding a project against deleted
infrastructure.
"""

from __future__ import annotations

import logging

import typer

from skaal.cli._errors import cli_error_boundary

app = typer.Typer(
    help="Scaffold a new Skaal project.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def init() -> None:
    log.error(
        "`skaal init` is not yet implemented in 0.4.0-alpha. "
        "The project scaffolder is rewritten in Phase 5 of ADR 028."
    )
    raise typer.Exit(1)
