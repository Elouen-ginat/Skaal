"""`skaal doctor` — check the toolchain is wired up correctly."""

from __future__ import annotations

import logging
import shutil
import sys

import typer

from skaal.cli._errors import cli_error_boundary

app = typer.Typer(
    help="Check the local Skaal toolchain (Python version, Pulumi availability).",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def doctor() -> None:
    """Report the local Skaal toolchain status."""
    log.info("Python: %s", sys.version.split()[0])
    pulumi = shutil.which("pulumi")
    log.info("Pulumi CLI: %s", pulumi or "not found on PATH")

    try:
        import skaal

        log.info("Skaal: %s", skaal.__version__)
    except Exception as exc:
        log.error("Skaal package failed to import: %s", exc)
        raise typer.Exit(1) from exc
