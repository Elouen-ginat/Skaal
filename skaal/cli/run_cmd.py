"""`skaal run` — execute the app on the local runtime.

The run verb walks `infer → bind → LocalRuntime.from_bound_plan` and
serves the resulting Starlette app via uvicorn. The pipeline is the
same one the deploy layer uses to generate cloud artefacts (ADR 032);
this verb just stops short at the local-runtime step.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

import typer

from skaal.cli._errors import cli_error_boundary

app = typer.Typer(
    help="Run a Skaal app locally.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def run(
    target: str = typer.Argument(
        ...,
        help=(
            "Dotted module:attribute pointing at an `App` instance, e.g. "
            "`examples.todo_api:app`."
        ),
    ),
    env_name: str = typer.Option(
        "local",
        "--env",
        "-e",
        help="Environment name from `skaal.toml` (defaults to `local`).",
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port."),
) -> None:
    skaal_app = _load_app(target)
    bound = _load_bound_plan(skaal_app, env_name)
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


def _load_app(target: str) -> Any:
    if ":" not in target:
        raise typer.BadParameter(
            f"`{target}` is not a `module:attribute` reference. "
            "Example: `examples.todo_api:app`."
        )
    module_path, attr = target.split(":", 1)
    module = importlib.import_module(module_path)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise typer.BadParameter(
            f"Module `{module_path}` has no attribute `{attr}`."
        ) from exc


def _load_bound_plan(skaal_app: Any, env_name: str) -> Any:
    from skaal.binding import bind, load_environment, load_lock

    env = load_environment(env_name, path=Path("skaal.toml"))
    lock = load_lock(Path("skaal.lock"))
    plan = skaal_app.infer()
    return bind(plan, env, lock)
