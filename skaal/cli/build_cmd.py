"""`skaal build` — generate Pulumi programs + Dockerfiles from a bound plan.

Code generation is rewired on the new `BoundPlan` in Phase 4 of ADR 028;
until then this command surfaces a clear error.
"""

from __future__ import annotations

import logging

import typer

from skaal.cli._errors import cli_error_boundary

app = typer.Typer(
    help="Generate deployment artifacts from a bound plan.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def build() -> None:
    log.error(
        "`skaal build` is not yet implemented in 0.4.0-alpha. "
        "Artifact generation is rewired on the bound-plan pipeline in "
        "Phase 4 of ADR 028."
    )
    raise typer.Exit(1)
