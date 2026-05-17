"""`skaal deploy` — package and deploy previously-built artifacts.

Reads ``skaal-meta.json`` from the artifacts directory to detect the target
platform, then packages and runs ``pulumi up`` in one cross-platform step.

Works on Windows, macOS, and Linux — no shell scripts required.

Defaults are resolved from (highest to lowest priority):
  CLI flags > SKAAL_* env vars > .skaal.env > [tool.skaal] in pyproject.toml.

Multi-app projects:

  skaal deploy --all          — every app in [tool.skaal.apps] in topo order.
  skaal deploy <app_name>     — single app declared in [tool.skaal.apps];
                                upstream URLs are read from
                                plan.skaal.project.lock.

Example pyproject.toml::

    [tool.skaal]
    stack       = "prod"
    region      = "eu-west-1"
    gcp_project = "my-project"    # GCP only

Then::

    skaal deploy
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from skaal.cli._errors import cli_error_boundary

app = typer.Typer(help="Package and deploy previously-built artifacts.")
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def deploy(
    app_name: str | None = typer.Argument(
        None,
        help=(
            "Name of an app declared in [tool.skaal.apps]. "
            "When omitted and --all is not set, deploys from --artifacts-dir."
        ),
        metavar="[APP_NAME]",
    ),
    all_apps: bool = typer.Option(
        False,
        "--all",
        help="Deploy every app declared in [tool.skaal.apps] in topological order.",
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
    region: str | None = typer.Option(
        None,
        "--region",
        "-r",
        help="Cloud region override. Env: SKAAL_REGION. pyproject: tool.skaal.region.",
    ),
    gcp_project: str | None = typer.Option(
        None,
        "--gcp-project",
        help=(
            "GCP project ID (required for GCP target). "
            "Env: SKAAL_GCP_PROJECT. pyproject: tool.skaal.gcp_project."
        ),
    ),
    yes: bool = typer.Option(
        True,
        "--yes/--no-yes",
        help="Pass --yes to pulumi up (non-interactive).",
    ),
) -> None:
    """
    Package the app and deploy it using Pulumi.

    Reads ``skaal-meta.json`` from the artifacts directory to detect the
    target platform (AWS Lambda or GCP Cloud Run), then:

    \b
    AWS  — installs deps, packages handler.py + source, runs pulumi up.
    GCP  — runs pulumi up (infra), builds + pushes Docker image, runs pulumi up.

        Prerequisites:
            AWS: AWS credentials configured.
            GCP: Application Default Credentials configured and a reachable Docker daemon.
    """
    from skaal import api

    if all_apps:
        steps = api.deploy_all(yes=yes)
        _summarize(steps)
        if any(not s.success for s in steps):
            raise typer.Exit(code=1)
        return

    if app_name is not None:
        from skaal.cli._orchestrator import deploy_all as _deploy_all
        from skaal.cli._orchestrator import hydrate_env_from_lock

        graph = api.project_graph()
        if app_name not in graph.apps:
            raise ValueError(
                f"App {app_name!r} is not declared in [tool.skaal.apps].\n"
                f"  Known apps: {sorted(graph.apps)}."
            )
        hydrate_env_from_lock(graph, app_name)
        steps = _deploy_all(graph, only=[app_name], yes=yes)
        _summarize(steps)
        if any(not s.success for s in steps):
            raise typer.Exit(code=1)
        return

    log.debug("Deploying artifacts from %s", artifacts_dir)
    api.deploy(
        artifacts_dir=artifacts_dir,
        stack=stack,
        region=region,
        gcp_project=gcp_project,
        yes=yes,
    )


def _summarize(steps: list) -> None:
    """Print one line per orchestration step."""
    for step in steps:
        marker = "OK " if step.success else "FAIL"
        suffix = step.url or step.error or "-"
        log.info("[%s] %s %s", marker, step.name, suffix)
