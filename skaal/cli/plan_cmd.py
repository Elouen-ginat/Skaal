"""`skaal plan` — walk the app graph and emit an `InferredPlan`.

The inference layer (ADR 028 §6.3) lands in Phase 2; until then this
command surfaces a clear error so the verb shows up in `skaal --help`
without claiming to do anything.
"""

from __future__ import annotations

import logging

import typer

from skaal.cli._errors import cli_error_boundary

app = typer.Typer(
    help="Walk the app and emit an InferredPlan.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def plan() -> None:
    log.error(
        "`skaal plan` is not yet implemented in 0.4.0-alpha. "
        "The inference layer lands in Phase 2 of ADR 028."
    )
    raise typer.Exit(1)
