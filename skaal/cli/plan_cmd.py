"""`skaal plan` — render the environment diff implied by the current app.

Phase 6 starts by diffing the current `BoundPlan` against `skaal.lock` for
the requested environment. Live deployed-state reconciliation, `skaal map`,
and `where` / `trace` land in follow-ups.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from skaal.binding import load_lock
from skaal.binding.model import BoundPlan, BoundResource, LockEntry, LockFile
from skaal.cli._errors import cli_error_boundary
from skaal.cli._load import load_app, load_plan

app = typer.Typer(
    help="Render the diff between the current app and `skaal.lock`.",
    context_settings={"allow_interspersed_args": True},
)
_MIXED_FINGERPRINT = "mixed"


@dataclass(frozen=True)
class PlanChange:
    """One create / update / delete row in the rendered plan diff."""

    action: str
    resource_id: str
    kind: str
    backend: str
    region: str | None
    details: str


@dataclass(frozen=True)
class PlanDiff:
    """The current bound plan plus its changes against `skaal.lock`."""

    bound: BoundPlan
    deployed_fingerprint: str | None
    changes: tuple[PlanChange, ...]


@app.callback(invoke_without_command=True)
@cli_error_boundary
def plan(
    target: str = typer.Argument(
        ...,
        help=(
            "Dotted module:attribute pointing at an `App` instance, e.g. `examples.todo_api:app`."
        ),
    ),
    env_name: str = typer.Option(
        "local",
        "--env",
        "-e",
        help="Environment name from `skaal.toml` (defaults to `local`).",
    ),
) -> None:
    skaal_app = load_app(target)
    loaded_plan = load_plan(skaal_app, env_name)
    lock = load_lock(Path("skaal.lock"))
    _render(_diff(loaded_plan.bound, lock))


def _diff(bound: BoundPlan, lock: LockFile) -> PlanDiff:
    """Return the current-vs-locked diff for deployable resources."""
    current = {
        resource.inferred.id: resource
        for resource in bound.resources
        if not resource.external
    }
    locked = {
        resource_id: entry
        for (env_name, resource_id), entry in lock.entries.items()
        if env_name == bound.environment
    }

    changes: list[PlanChange] = []

    for resource_id in sorted(current.keys() - locked.keys()):
        resource = current[resource_id]
        changes.append(
            PlanChange(
                action="create",
                resource_id=resource_id,
                kind=resource.inferred.kind.value,
                backend=resource.backend,
                region=resource.region,
                details="new resource",
            )
        )

    for resource_id in sorted(current.keys() & locked.keys()):
        resource = current[resource_id]
        entry = locked[resource_id]
        details = _update_details(resource, entry, bound.bound_fingerprint)
        if details:
            changes.append(
                PlanChange(
                    action="update",
                    resource_id=resource_id,
                    kind=resource.inferred.kind.value,
                    backend=resource.backend,
                    region=resource.region,
                    details=details,
                )
            )

    for resource_id in sorted(locked.keys() - current.keys()):
        entry = locked[resource_id]
        changes.append(
            PlanChange(
                action="delete",
                resource_id=resource_id,
                kind="-",
                backend=entry.backend,
                region=entry.region,
                details="resource no longer exists in code",
            )
        )

    return PlanDiff(
        bound=bound,
        deployed_fingerprint=_deployed_fingerprint(locked.values()),
        changes=tuple(changes),
    )


def _update_details(resource: BoundResource, entry: LockEntry, fingerprint: str) -> str:
    """Describe how `resource` differs from its locked snapshot."""
    details: list[str] = []
    if entry.backend != resource.backend:
        details.append(f"backend {entry.backend} -> {resource.backend}")
    if entry.region != resource.region:
        details.append(f"region {_display(entry.region)} -> {_display(resource.region)}")
    if entry.fingerprint != fingerprint:
        details.append(f"fingerprint {_display(entry.fingerprint)} -> {fingerprint}")
    return "; ".join(details)


def _deployed_fingerprint(entries: Iterable[LockEntry]) -> str | None:
    """Collapse per-resource lock fingerprints into one display value."""
    values = {entry.fingerprint for entry in entries if entry.fingerprint}
    if len(values) == 1:
        return next(iter(values))
    if len(values) > 1:
        return _MIXED_FINGERPRINT
    return None


def _display(value: str | None) -> str:
    """Render optional CLI values consistently."""
    return value or "-"


def _render(diff: PlanDiff) -> None:
    console = Console()
    console.print(
        f"[bold]{diff.bound.app}[/bold] / env=[cyan]{diff.bound.environment}[/cyan]  "
        f"app={diff.bound.app_fingerprint or '-'}  "
        f"current={diff.bound.bound_fingerprint or '-'}  "
        f"deployed={diff.deployed_fingerprint or '-'}"
    )

    if not diff.bound.resources:
        console.print("[dim]No resources discovered.[/dim]")
        return

    if not diff.changes:
        console.print("[green]No changes.[/green] `skaal.lock` already matches this plan.")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Action")
    table.add_column("Resource")
    table.add_column("Kind")
    table.add_column("Backend")
    table.add_column("Region")
    table.add_column("Details")

    for change in diff.changes:
        table.add_row(
            change.action,
            change.resource_id,
            change.kind,
            change.backend,
            change.region or "-",
            change.details,
        )

    console.print(table)
