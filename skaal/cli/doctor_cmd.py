"""`skaal doctor` — check the toolchain is wired up correctly."""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

import typer

from skaal.cli._errors import cli_error_boundary

app = typer.Typer(
    help="Check the local Skaal toolchain (Python version, Pulumi availability).",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")


@app.callback(invoke_without_command=True)
@cli_error_boundary
def doctor() -> None:
    """Report the local Skaal toolchain status."""
    log.info("Python: %s", sys.version.split()[0])
    pulumi = shutil.which("pulumi")
    log.info("Pulumi CLI: %s", pulumi or "not found on PATH")
    docker = shutil.which("docker")
    log.info("Docker CLI: %s", docker or "not found on PATH")
    log.info("AWS auth: %s", _aws_auth_source())
    log.info(
        "AWS region: %s", os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "not set"
    )

    try:
        import skaal

        log.info("Skaal: %s", skaal.__version__)
    except Exception as exc:
        log.error("Skaal package failed to import: %s", exc)
        raise typer.Exit(1) from exc


def _aws_auth_source() -> str:
    """Describe which AWS credential source is currently visible."""
    if os.getenv("AWS_ACCESS_KEY_ID"):
        return "env"

    profile = os.getenv("AWS_PROFILE")
    if profile:
        return f"profile:{profile}"

    aws_dir = Path.home() / ".aws"
    if (aws_dir / "credentials").exists() or (aws_dir / "config").exists():
        return "shared-config"

    return "not-detected"
