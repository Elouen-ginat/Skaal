"""Shared `Plan` diff shapes used by the CLI, API, and PR comments."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from skaal.binding.model import LockEntry, LockFile, Plan, PlannedResource

MIXED_FINGERPRINT_MARKER = "mixed"


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
    """The current plan plus its changes against `skaal.lock`."""

    bound: Plan
    deployed_fingerprint: str | None
    changes: tuple[PlanChange, ...]


def diff_plan(bound: Plan, lock: LockFile) -> PlanDiff:
    """Return the current-vs-locked diff for deployable resources.

    Args:
        bound: Bound plan for the requested app and environment.
        lock: Parsed lock file snapshot.

    Returns:
        The plan diff against the lock entries for the same environment.
    """
    current = {
        resource.inferred.id: resource for resource in bound.resources if not resource.external
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
        deployed_fingerprint=deployed_fingerprint(locked.values()),
        changes=tuple(changes),
    )


def diff_bound_plans(current: Plan, baseline: Plan) -> PlanDiff:
    """Return the structural diff between two bound plans.

    Args:
        current: Bound plan for the current checkout / ref.
        baseline: Bound plan for the comparison checkout / ref.

    Returns:
        A diff whose `changes` describe creates, updates, and deletes needed
        to move from `baseline` to `current`.
    """
    current_resources = {
        resource.inferred.id: resource for resource in current.resources if not resource.external
    }
    baseline_resources = {
        resource.inferred.id: resource for resource in baseline.resources if not resource.external
    }

    changes: list[PlanChange] = []

    for resource_id in sorted(current_resources.keys() - baseline_resources.keys()):
        resource = current_resources[resource_id]
        changes.append(
            PlanChange(
                action="create",
                resource_id=resource_id,
                kind=resource.inferred.kind.value,
                backend=resource.backend,
                region=resource.region,
                details="new resource in head",
            )
        )

    for resource_id in sorted(current_resources.keys() & baseline_resources.keys()):
        resource = current_resources[resource_id]
        baseline_resource = baseline_resources[resource_id]
        details = _update_bound_details(resource, baseline_resource)
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

    for resource_id in sorted(baseline_resources.keys() - current_resources.keys()):
        resource = baseline_resources[resource_id]
        changes.append(
            PlanChange(
                action="delete",
                resource_id=resource_id,
                kind=resource.inferred.kind.value,
                backend=resource.backend,
                region=resource.region,
                details="resource only exists in base",
            )
        )

    return PlanDiff(
        bound=current,
        deployed_fingerprint=baseline.bound_fingerprint or None,
        changes=tuple(changes),
    )


def deployed_fingerprint(entries: Iterable[LockEntry]) -> str | None:
    """Collapse per-resource lock fingerprints into one display value.

    Args:
        entries: Lock entries for one environment.

    Returns:
        The shared fingerprint, `mixed`, or `None` when no fingerprint exists.
    """
    first: str | None = None
    for entry in entries:
        if not entry.fingerprint:
            continue
        if first is None:
            first = entry.fingerprint
            continue
        if entry.fingerprint != first:
            return MIXED_FINGERPRINT_MARKER
    return first


def display_optional(value: str | None) -> str:
    """Render optional CLI/API values consistently.

    Args:
        value: Optional string value.

    Returns:
        The value or `-` when unset.
    """
    return value or "-"


def render_plan_diff_markdown(
    diff: PlanDiff,
    *,
    compared_label: str = "deployed",
) -> str:
    """Render `diff` as GitHub-flavored markdown.

    Args:
        diff: Diff to render.
        compared_label: Human label for `diff.deployed_fingerprint`.

    Returns:
        A markdown summary suitable for CLI output or PR comments.
    """
    lines = [
        f"- app: `{_escape_inline(diff.bound.app)}`",
        f"- env: `{_escape_inline(diff.bound.environment)}`",
        f"- current: `{_escape_inline(diff.bound.bound_fingerprint or '-')}`",
        f"- {compared_label}: `{_escape_inline(diff.deployed_fingerprint or '-')}`",
        "",
    ]

    if not diff.bound.resources:
        lines.append("No resources discovered.")
        return "\n".join(lines) + "\n"

    if not diff.changes:
        lines.append("No infrastructure changes.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Action | Resource | Kind | Backend | Region | Details |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    lines.extend(
        "| "
        + " | ".join(
            [
                _escape_cell(change.action),
                _escape_code_cell(change.resource_id),
                _escape_code_cell(change.kind),
                _escape_code_cell(change.backend),
                _escape_code_cell(change.region or "-"),
                _escape_cell(change.details),
            ]
        )
        + " |"
        for change in diff.changes
    )
    return "\n".join(lines) + "\n"


def _update_details(resource: PlannedResource, entry: LockEntry, bound_fingerprint: str) -> str:
    """Describe how `resource` differs from its locked snapshot."""
    details: list[str] = []
    if entry.backend != resource.backend:
        details.append(f"backend {entry.backend} -> {resource.backend}")
    if entry.region != resource.region:
        details.append(
            f"region {display_optional(entry.region)} -> {display_optional(resource.region)}"
        )
    if entry.fingerprint is None:
        details.append(f"fingerprint unrecorded -> {bound_fingerprint}")
    elif entry.fingerprint != bound_fingerprint:
        details.append(f"fingerprint {display_optional(entry.fingerprint)} -> {bound_fingerprint}")
    return "; ".join(details)


def _update_bound_details(resource: PlannedResource, baseline: PlannedResource) -> str:
    """Describe how `resource` differs from `baseline`."""
    details: list[str] = []
    if baseline.inferred.kind != resource.inferred.kind:
        details.append(f"kind {baseline.inferred.kind.value} -> {resource.inferred.kind.value}")
    if baseline.backend != resource.backend:
        details.append(f"backend {baseline.backend} -> {resource.backend}")
    if baseline.region != resource.region:
        details.append(
            f"region {display_optional(baseline.region)} -> {display_optional(resource.region)}"
        )
    return "; ".join(details)


def _escape_inline(value: str) -> str:
    """Escape inline-code content used in markdown summaries."""
    return value.replace("`", "\\`")


def _escape_cell(value: str) -> str:
    """Escape markdown table cell content."""
    return value.replace("|", "\\|").replace("\n", "<br>")


def _escape_code_cell(value: str) -> str:
    """Escape markdown table cell content wrapped in backticks."""
    return f"`{_escape_cell(_escape_inline(value))}`"
