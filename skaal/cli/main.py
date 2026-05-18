"""Entry point for the `skaal` CLI.

The CLI surface in `0.4.0-alpha` is:

    - `init`, `run`, `plan`, `map`, `where`, `trace`, `build`, `deploy`,
        `destroy`, `stubs`, `doctor`

`rebind`, `unbind`, `backends`, `diff`, `infra`, `stacks`, `catalog` are
scheduled for their respective later phases and are not registered here.
"""

import sys

import typer

from skaal.cli._logging import LogFormat, configure_cli_logging
from skaal.cli._params import Option
from skaal.cli.build_cmd import app as build_app
from skaal.cli.deploy_cmd import app as deploy_app
from skaal.cli.destroy_cmd import app as destroy_app
from skaal.cli.doctor_cmd import app as doctor_app
from skaal.cli.init_cmd import app as init_app
from skaal.cli.map_cmd import app as map_app
from skaal.cli.plan_cmd import app as plan_app
from skaal.cli.run_cmd import app as run_app
from skaal.cli.stubs_cmd import app as stubs_app
from skaal.cli.trace_cmd import app as trace_app
from skaal.cli.where_cmd import app as where_app

app = typer.Typer(
    name="skaal",
    help="Skaal — a Python framework where the application code is the infrastructure declaration.",
    no_args_is_help=True,
)

app.add_typer(init_app, name="init")
app.add_typer(run_app, name="run")
app.add_typer(plan_app, name="plan")
app.add_typer(map_app, name="map")
app.add_typer(where_app, name="where")
app.add_typer(trace_app, name="trace")
app.add_typer(build_app, name="build")
app.add_typer(deploy_app, name="deploy")
app.add_typer(destroy_app, name="destroy")
app.add_typer(stubs_app, name="stubs")
app.add_typer(doctor_app, name="doctor")


def _force_utf8_streams() -> None:
    """Reconfigure stdout/stderr to UTF-8 so Rich output (box-drawing
    characters, arrows, etc.) renders on Windows consoles whose default
    code page is `cp1252`. Without this, `console.print("foo → bar")`
    crashes with `UnicodeEncodeError: 'charmap'` on a default Windows
    install.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


@app.callback()
def _root(
    verbose: int = Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase log verbosity. -v=INFO, -vv=DEBUG.",
    ),
    quiet: bool = Option(
        False,
        "--quiet",
        "-q",
        help="Suppress INFO logs. Errors still print.",
    ),
    log_format: LogFormat | None = Option(
        None,
        "--log-format",
        help="text or json. Env: SKAAL_LOG_FORMAT.",
        case_sensitive=False,
    ),
) -> None:
    _force_utf8_streams()
    configure_cli_logging(verbose=verbose, quiet=quiet, fmt=log_format)


if __name__ == "__main__":
    app()
