"""`skim deploy` — apply plan to target infrastructure via Pulumi."""

from __future__ import annotations

import typer

app = typer.Typer(help="Deploy the app to the target infrastructure.")


@app.callback(invoke_without_command=True)
def deploy(
    preview: bool = typer.Option(False, "--preview", help="Dry run — show what would change."),
    rollback: bool = typer.Option(False, "--rollback", help="Roll back to the previous version."),
    version: int = typer.Option(2, "--version", help="Target version to deploy."),
) -> None:
    """Apply plan.skim.lock to real infrastructure using Pulumi Automation API."""
    raise NotImplementedError("`skim deploy` is not yet implemented (Phase 3).")
