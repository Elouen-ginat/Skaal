"""`skaal doctor` — check the toolchain is wired up correctly."""

from __future__ import annotations

import logging
import shutil
import sys

import typer
from rich.console import Console
from rich.table import Table

from skaal.binding._probe import (
    detect_aws_auth,
    detect_docker_daemon,
    detect_gcp_auth,
    resolve_aws_region,
    resolve_gcp_project,
)
from skaal.binding.environment import load_environment, load_environments
from skaal.binding.model import Environment, Target
from skaal.cli._errors import cli_error_boundary
from skaal.cli._params import Option
from skaal.settings import get_settings

app = typer.Typer(
    help="Check the local Skaal toolchain (Python version, Pulumi availability).",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def doctor(
    env_name: str | None = Option(
        None,
        "--env",
        "-e",
        help=(
            "Environment from `skaal.toml` to focus on. When omitted, falls back "
            "to ``[tool.skaal].env`` / ``SKAAL_ENV``; if still unset, every "
            "environment defined in `skaal.toml` is reported."
        ),
    ),
) -> None:
    """Report the local Skaal toolchain status."""
    console = Console()
    _print_toolchain(console)

    resolved = env_name or get_settings().env
    if resolved is not None:
        env = load_environment(resolved)
        _print_environment(console, env)
        return

    config = load_environments()
    envs = config.list_environments()
    if not envs:
        return
    for env in envs.values():
        _print_environment(console, env)


def _print_toolchain(console: Console) -> None:
    table = Table(title="Toolchain", title_justify="left", show_header=False, expand=False)
    table.add_column("Tool", style="bold cyan", no_wrap=True)
    table.add_column("Value")

    try:
        import skaal

        skaal_version = skaal.__version__
    except Exception as exc:  # pragma: no cover - import failure
        log.error("Skaal package failed to import: %s", exc)
        raise typer.Exit(1) from exc

    table.add_row("Python", sys.version.split()[0])
    table.add_row("Skaal", skaal_version)
    table.add_row("Pulumi CLI", shutil.which("pulumi") or _missing("not on PATH"))
    table.add_row("Docker", _docker_status())
    console.print(table)


def _docker_status() -> str:
    state = detect_docker_daemon()
    path = shutil.which("docker")
    if state == "running":
        return f"{path} [dim](daemon up)[/dim]"
    if state == "not-installed":
        return _missing("not on PATH")
    return f"{path} [yellow](daemon not running)[/yellow]"


def _print_environment(console: Console, env: Environment) -> None:
    title = f"Environment: [bold]{env.name}[/bold]  ([cyan]{env.target.value}[/cyan])"
    table = Table(title=title, title_justify="left", show_header=False, expand=False)
    table.add_column("Setting", style="bold cyan", no_wrap=True)
    table.add_column("Value")

    if env.target is Target.AWS:
        if env.region:
            table.add_row("region", f"{env.region} [dim](skaal.toml)[/dim]")
        elif aws_region := resolve_aws_region(None):
            table.add_row("region", f"{aws_region} [dim](env var)[/dim]")
        else:
            table.add_row("region", _missing("not set"))
        table.add_row("AWS auth", _annotate_auth(detect_aws_auth()))
    elif env.target is Target.GCP:
        table.add_row("region", env.region or _missing("not set"))
        table.add_row("GCP project", _gcp_project_value(env, resolve_gcp_project(env)))
        table.add_row("GCP auth", _annotate_auth(detect_gcp_auth()))
    elif env.region:
        table.add_row("region", env.region)

    console.print(table)


def _annotate_auth(source: str) -> str:
    """Wrap the canonical ``not-detected`` sentinel from the probes in yellow."""
    return _missing("not detected") if source == "not-detected" else source


def _gcp_project_value(env: Environment, project: str | None) -> str:
    if project is None:
        return _missing(
            "not set — add it under "
            f"[env.{env.name}.backends.gcp].project in `skaal.toml` "
            "or export GOOGLE_CLOUD_PROJECT"
        )
    gcp_backend = env.backends.get("gcp")
    source = "skaal.toml" if gcp_backend and gcp_backend.project else "env var"
    return f"{project} [dim]({source})[/dim]"


def _missing(reason: str) -> str:
    return f"[yellow]{reason}[/yellow]"
