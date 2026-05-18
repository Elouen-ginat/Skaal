"""`skaal map` — print the source-to-resource tree for an environment."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import typer
from rich.console import Console
from rich.tree import Tree

from skaal.api import ResourceMap, ResourceMapEntry
from skaal.cli._errors import cli_error_boundary
from skaal.cli._load import load_app, load_plan
from skaal.cli._params import Argument, Option

app = typer.Typer(
    help="Print the source-to-resource tree and emit `.skaal/map.json`.",
    context_settings={"allow_interspersed_args": True},
)


@app.callback(invoke_without_command=True)
@cli_error_boundary
def map(
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
    out_path: Path = Option(
        Path(".skaal/map.json"),
        "--out",
        "-o",
        help="Path to the emitted JSON resource map.",
    ),
) -> None:
    skaal_app = load_app(target)
    loaded_plan = load_plan(skaal_app, env_name)
    resource_map = ResourceMap.for_bound_plan(loaded_plan.bound)
    _write(resource_map, out_path)
    _render(resource_map, out_path)


def _write(resource_map: ResourceMap, out_path: Path) -> None:
    """Write the JSON sidecar to disk."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(resource_map.to_json(), encoding="utf-8")


def _render(resource_map: ResourceMap, out_path: Path) -> None:
    """Render the tree view to the terminal."""
    console = Console()
    console.print(
        f"[bold]{resource_map.app}[/bold] / env=[cyan]{resource_map.environment}[/cyan]  "
        f"app={resource_map.app_fingerprint or '-'}  bound={resource_map.bound_fingerprint or '-'}"
    )
    if not resource_map.resources:
        console.print("[dim]No resources discovered.[/dim]")
        console.print(f"Wrote [cyan]{out_path}[/cyan]")
        return

    tree = Tree(resource_map.app)
    cwd = Path.cwd().resolve()
    by_file: dict[str, list[ResourceMapEntry]] = defaultdict(list)
    for entry in resource_map.resources:
        by_file[_display_file(entry.file, cwd)].append(entry)

    for file_name in sorted(by_file):
        file_branch = tree.add(file_name)
        for entry in by_file[file_name]:
            file_branch.add(_entry_label(entry))

    console.print(tree)
    console.print(f"Wrote [cyan]{out_path}[/cyan]")


def _display_file(raw: str, cwd: Path) -> str:
    """Display `raw` relative to cwd when possible."""
    path = Path(raw)
    try:
        return str(path.resolve().relative_to(cwd))
    except ValueError:
        # Different roots (or already-synthetic paths like `<unknown>`) cannot
        # be relativized; falling back to the basename keeps the tree compact.
        return path.name or path.stem or raw


def _entry_label(entry: ResourceMapEntry) -> str:
    """Render one resource leaf."""
    extras: list[str] = [entry.backend]
    if entry.region:
        extras.append(entry.region)
    if entry.external:
        extras.append("external")
    elif entry.pinned:
        extras.append("pinned")
    return (
        f"{entry.qualname} [dim](line {entry.line})[/dim] → "
        f"{entry.kind.value} [cyan]{', '.join(extras)}[/cyan]"
    )
