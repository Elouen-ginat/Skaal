"""`skaal destroy` — destroy previously-deployed Pulumi resources."""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from skaal.cli._errors import cli_error_boundary

app = typer.Typer(help="Destroy previously-deployed Pulumi resources.")
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def destroy(
    app_name: str | None = typer.Argument(
        None,
        help="Name of an app declared in [tool.skaal.apps] to destroy only.",
        metavar="[APP_NAME]",
    ),
    all_apps: bool = typer.Option(
        False,
        "--all",
        help="Destroy every app declared in [tool.skaal.apps] in reverse topological order.",
    ),
    artifacts_dir: Path = typer.Option(
        Path("artifacts"),
        "--artifacts-dir",
        "-a",
        help="Path to the artifacts directory produced by `skaal build`.",
    ),
    stack: str | None = typer.Option(
        None,
        "--stack",
        "-s",
        help="Pulumi stack name. Env: SKAAL_STACK. pyproject: tool.skaal.stack.",
    ),
    yes: bool = typer.Option(
        True,
        "--yes/--no-yes",
        help="Pass --yes to pulumi destroy (non-interactive).",
    ),
) -> None:
    """Destroy the app resources tracked by the Pulumi stack."""
    from skaal import api
    from skaal.cli.config import SkaalSettings

    if all_apps:
        steps = api.destroy_all(yes=yes)
        for step in steps:
            marker = "OK " if step.success else "FAIL"
            suffix = step.error or "-"
            log.info("[%s] %s %s", marker, step.name, suffix)
        if any(not s.success for s in steps):
            raise typer.Exit(code=1)
        return

    if app_name and app_name in SkaalSettings().apps:
        from skaal.cli._orchestrator import destroy_all as _destroy_all

        graph = api.project_graph()
        steps = _destroy_all(graph, only=[app_name], yes=yes)
        for step in steps:
            marker = "OK " if step.success else "FAIL"
            log.info("[%s] %s", marker, step.name)
        if any(not s.success for s in steps):
            raise typer.Exit(code=1)
        return

    log.debug("Destroying stack from %s", artifacts_dir)
    api.destroy(
        artifacts_dir=artifacts_dir,
        stack=stack,
        yes=yes,
    )
