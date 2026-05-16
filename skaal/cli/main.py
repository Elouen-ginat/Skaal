"""Entry point for the `skaal` CLI.

The CLI surface in `0.4.0-alpha` is:

  - `init`, `run`, `plan`, `map`, `build`, `deploy`, `stubs`, `doctor`

`map`, `where`, `trace`, `rebind`, `unbind`, `backends`, `diff`,
`destroy`, `infra`, `stacks`, `catalog` are scheduled for their respective
later phases and are not registered here.
"""

import typer

from skaal.cli._logging import LogFormat, configure_cli_logging
from skaal.cli.build_cmd import app as build_app
from skaal.cli.deploy_cmd import app as deploy_app
from skaal.cli.doctor_cmd import app as doctor_app
from skaal.cli.init_cmd import app as init_app
from skaal.cli.map_cmd import app as map_app
from skaal.cli.plan_cmd import app as plan_app
from skaal.cli.run_cmd import app as run_app
from skaal.cli.stubs_cmd import app as stubs_app

app = typer.Typer(
    name="skaal",
    help="Skaal — a Python framework where the application code is the infrastructure declaration.",
    no_args_is_help=True,
)

app.add_typer(init_app, name="init")
app.add_typer(run_app, name="run")
app.add_typer(plan_app, name="plan")
app.add_typer(map_app, name="map")
app.add_typer(build_app, name="build")
app.add_typer(deploy_app, name="deploy")
app.add_typer(stubs_app, name="stubs")
app.add_typer(doctor_app, name="doctor")


@app.callback()
def _root(
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase log verbosity. -v=INFO, -vv=DEBUG.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress INFO logs. Errors still print.",
    ),
    log_format: LogFormat | None = typer.Option(
        None,
        "--log-format",
        help="text or json. Env: SKAAL_LOG_FORMAT.",
        case_sensitive=False,
    ),
) -> None:
    configure_cli_logging(verbose=verbose, quiet=quiet, fmt=log_format)


if __name__ == "__main__":
    app()
