"""`skaal deploy` — provision infrastructure via Pulumi and pin `skaal.lock`.

The deploy verb is rewired on the new `BoundPlan` / `skaal.lock`
binding pipeline in Phase 4 of ADR 028; until then this command surfaces
a clear error.
"""

from __future__ import annotations

import logging

import typer

from skaal.cli._errors import cli_error_boundary

app = typer.Typer(
    help="Provision infrastructure via Pulumi.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def deploy() -> None:
    log.error(
        "`skaal deploy` is not yet implemented in 0.4.0-alpha. "
        "The deploy pipeline lands in Phase 4 of ADR 028."
    )
    raise typer.Exit(1)
