"""Shared `BoundPlan` diff shapes used by the CLI and Python API."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from skaal.binding.model import BoundPlan, BoundResource, LockEntry, LockFile

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
    """The current bound plan plus its changes against `skaal.lock`."""

    bound: BoundPlan
    deployed_fingerprint: str | None
    changes: tuple[PlanChange, ...]


def diff_plan(bound: BoundPlan, lock: LockFile) -> PlanDiff:
    """Return the current-vs-locked diff for deployable resources.

    Args:
        bound: Bound plan for the requested app and environment.
        lock: Parsed lock file snapshot.

    Returns:
        The plan diff against the lock entries for the same environment.
    """
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
        deployed_fingerprint=deployed_fingerprint(locked.values()),
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


def _update_details(resource: BoundResource, entry: LockEntry, bound_fingerprint: str) -> str:
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
