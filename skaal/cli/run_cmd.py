"""`skaal run` — execute the app on the local runtime.

The run verb walks `infer → bind → LocalRuntime.from_bound_plan` and
serves the resulting Starlette app via uvicorn. The pipeline is the
same one the deploy layer uses to generate cloud artefacts (ADR 032);
this verb just stops short at the local-runtime step.
"""

from __future__ import annotations

import logging

import typer

from skaal.cli._errors import cli_error_boundary
from skaal.cli._load import load_app, load_bound_plan
from skaal.cli._params import Argument, Option
from skaal.settings import get_settings

app = typer.Typer(
    help="Run a Skaal app locally.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def run(
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
    host: str | None = Option(None, "--host", help="Bind host."),
    port: int | None = Option(None, "--port", "-p", help="Bind port."),
) -> None:
    skaal_app = load_app(target)
    settings = get_settings()
    bound = load_bound_plan(skaal_app, env_name, fallback_env="local")
    resolved_host = host or settings.run.host
    resolved_port = port if port is not None else settings.run.port
    log.info(
        "Serving app %r (env=%s, fingerprint=%s) on %s:%d",
        skaal_app.name,
        bound.environment,
        bound.bound_fingerprint,
        resolved_host,
        resolved_port,
    )

    from skaal.runtime import LocalRuntime

    LocalRuntime.from_bound_plan(bound, skaal_app).serve(host=resolved_host, port=resolved_port)
