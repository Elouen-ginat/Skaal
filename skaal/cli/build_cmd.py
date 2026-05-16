"""`skaal build` — render Pulumi-adjacent artefacts from a bound plan.

The verb walks ``infer → bind`` and feeds the resulting `BoundPlan` into
`skaal.deploy.build_artefacts`, which writes the per-Lambda Dockerfile,
handler, bootstrap, and requirements files to ``./.skaal/build/<env>/``.

`skaal build` does not invoke Pulumi; it is pure templating. `skaal
deploy` runs `build` and then drives the Pulumi Automation API against
the rendered tree.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console

from skaal.cli._errors import cli_error_boundary
from skaal.cli._load import AppSpec, load_app, load_plan
from skaal.deploy import build_artefacts

app = typer.Typer(
    help="Render deploy artefacts from a bound plan.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def build(
    target: str = typer.Argument(
        ...,
        help=(
            "Dotted module:attribute pointing at an `App` instance, e.g. `examples.todo_api:app`."
        ),
    ),
    env_name: str = typer.Option(
        "local",
        "--env",
        "-e",
        help="Environment name from `skaal.toml`.",
    ),
    out_dir: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help=("Destination directory for rendered artefacts. Defaults to `./.skaal/build/<env>`."),
    ),
    python_version: str = typer.Option(
        "3.11",
        "--python-version",
        help="Python minor version embedded in the Dockerfile base image.",
    ),
) -> None:
    try:
        app_spec = AppSpec.parse(target)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    skaal_app = load_app(app_spec)
    loaded = load_plan(skaal_app, env_name)

    written = build_artefacts(
        loaded.bound,
        loaded.env,
        app_spec,
        out_dir=out_dir,
        python_version=python_version,
    )

    artefact_count = sum(1 for r in loaded.bound.resources if not r.external)
    Console().print(
        f"Built [bold]{artefact_count}[/bold] resource artefact(s) for "
        f"[cyan]{env_name}[/cyan] → {written}"
    )
