"""`skaal run` — execute the app on the local runtime.

The local runtime is being rewritten on top of the inference / binding
pipeline (ADR 028 Phase 4). Until then this command surfaces a clear error
rather than running the deleted `0.3.x` runtime.
"""

from __future__ import annotations

import logging

import typer

from skaal.cli._errors import cli_error_boundary

app = typer.Typer(
    help="Run a Skaal app locally.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def run() -> None:
    log.error(
        "`skaal run` is not yet implemented in 0.4.0-alpha. "
        "The local runtime is rewritten on top of the new bound plan in "
        "Phase 4 of ADR 028."
    )
    raise typer.Exit(1)
