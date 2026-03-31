"""`skim run` — run the app locally, simulating distributed topology."""

from __future__ import annotations

import typer

app = typer.Typer(help="Run the Skim app locally.")


@app.callback(invoke_without_command=True)
def run(
    topology: int = typer.Option(1, "--topology", "-t", help="Number of simulated instances."),
) -> None:
    """Run the Skim app locally, simulating N instances in a single process."""
    raise NotImplementedError("`skim run` is not yet implemented (Phase 1).")
