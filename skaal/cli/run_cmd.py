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

app = typer.Typer(
    help="Run a Skaal app locally.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def run(
    target: str = Argument(
        ...,
        help=(
            "Dotted module:attribute pointing at an `App` instance, e.g. `examples.todo_api:app`."
        ),
    ),
    env_name: str = Option(
        "local",
        "--env",
        "-e",
        help="Environment name from `skaal.toml` (defaults to `local`).",
    ),
    host: str = Option("127.0.0.1", "--host", help="Bind host."),
    port: int = Option(8000, "--port", "-p", help="Bind port."),
) -> None:
    skaal_app = load_app(target)
    bound = load_bound_plan(skaal_app, env_name)
    log.info(
        "Serving app %r (env=%s, fingerprint=%s) on %s:%d",
        skaal_app.name,
        env_name,
        bound.bound_fingerprint,
        host,
        port,
    )

    from skaal.runtime import LocalRuntime

    LocalRuntime.from_bound_plan(bound, skaal_app).serve(host=host, port=port)
