"""``skaal stacks`` — list configured stack profiles.

Reads ``[tool.skaal.stacks.<name>]`` sections from the nearest
``pyproject.toml`` and prints one row per profile with the resolved region,
GCP project, and deploy target (after applying each profile over the base
settings).  Useful sanity-check before running ``skaal deploy --stack X``.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from skaal.settings import SkaalSettings

app = typer.Typer(help="List configured stack profiles.")


@app.callback(invoke_without_command=True)
def stacks() -> None:
    """Print one row per declared stack profile."""
    base = SkaalSettings()
    if not base.stacks:
        typer.echo(
            "No stacks configured. Add profiles under [tool.skaal.stacks.<name>] "
            "in pyproject.toml."
        )
        return

    console = Console()
    table = Table(show_header=True, header_style="bold")
    table.add_column("stack")
    table.add_column("target")
    table.add_column("region")
    table.add_column("gcp_project")
    table.add_column("protect")
    table.add_column("hooks")

    for name in sorted(base.stacks):
        cfg = base.for_stack(name)
        marker = "*" if name == base.stack else ""
        protect = (
            "yes"
            if cfg.deletion_protection is True
            else "no"
            if cfg.deletion_protection is False
            else "-"
        )
        hook_count = len(cfg.pre_deploy) + len(cfg.post_deploy)
        hooks = str(hook_count) if hook_count else "-"
        table.add_row(
            f"{marker}{name}",
            cfg.target,
            cfg.region,
            cfg.gcp_project or "-",
            protect,
            hooks,
        )

    console.print(table)
    if base.stack in base.stacks:
        console.print("* = current default stack (tool.skaal.stack)", style="dim")
