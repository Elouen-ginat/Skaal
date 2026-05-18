"""`skaal build` — render Pulumi-adjacent artefacts from a plan.

The verb walks ``blueprint → plan`` and feeds the resulting `Plan` into
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
from skaal.cli._load import load_app, load_plan, resolve_app_spec, resolve_build_out_dir
from skaal.cli._params import Argument, Option
from skaal.deploy import build_artefacts

app = typer.Typer(
    help="Render deploy artefacts from a bound plan.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def build(
    target: str | None = Argument(
        None,
        help=(
            "Dotted module:attribute pointing at an `App` instance. When omitted, "
            "falls back to `[tool.skaal].app` / `SKAAL_APP`."
        ),
    ),
    env_name: str | None = Option(
        None,
        "--env",
        "-e",
        help=(
            "Environment name from `skaal.toml`. When omitted, falls back to "
            "`[tool.skaal].default_environment` / `SKAAL_DEFAULT_ENVIRONMENT`, then `local`."
        ),
    ),
    out_dir: Path | None = Option(
        None,
        "--out",
        "-o",
        help=(
            "Destination directory for rendered artefacts. Defaults to "
            "`[tool.skaal].out/<env>` or `./.skaal/build/<env>`."
        ),
    ),
    python_version: str = Option(
        "3.11",
        "--python-version",
        help="Python minor version embedded in the Dockerfile base image.",
    ),
    dev: bool = Option(
        False,
        "--dev",
        help=(
            "Ship the local Skaal checkout inside each Lambda image instead of "
            "installing `skaal[...]` from PyPI. Use during the 0.4.0 alpha while "
            "the package is not yet published."
        ),
    ),
) -> None:
    app_spec = resolve_app_spec(target)
    skaal_app = load_app(app_spec)
    loaded = load_plan(skaal_app, env_name, fallback_env="local")
    resolved_out_dir = resolve_build_out_dir(out_dir, loaded.env.name)

    written = build_artefacts(
        loaded.bound,
        loaded.env,
        app_spec,
        out_dir=resolved_out_dir,
        python_version=python_version,
        dev=dev,
    )

    artefact_count = sum(1 for r in loaded.bound.resources if not r.external)
    Console().print(
        f"Built [bold]{artefact_count}[/bold] resource artefact(s) for "
        f"[cyan]{loaded.env.name}[/cyan] → {written}"
    )
