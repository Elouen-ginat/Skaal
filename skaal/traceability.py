"""Resolve resource ids and log lines back to inferred source locations."""

from __future__ import annotations

from dataclasses import dataclass

from skaal.binding.model import BoundPlan, BoundResource


@dataclass(frozen=True)
class TraceHit:
    """One resolved trace result."""

    resource: BoundResource
    matched_text: str


def resolve_trace(needle: str, bound: BoundPlan) -> TraceHit:
    """Resolve `needle` against the current bound plan.

    Args:
        needle: Resource id or log line containing a resource id.
        bound: Bound plan to search.

    Returns:
        The best matching bound resource and matched text.

    Raises:
        ValueError: If no resource id can be resolved from the input.
    """
    resources = bound.resources
    best_match: BoundResource | None = None
    for resource in resources:
        if needle == resource.inferred.id:
            return TraceHit(resource=resource, matched_text=resource.inferred.id)

    matches = [resource for resource in resources if resource.inferred.id in needle]
    if matches:
        best_match = max(matches, key=lambda resource: len(resource.inferred.id))
    if best_match is not None:
        return TraceHit(resource=best_match, matched_text=best_match.inferred.id)

    known_ids = ", ".join(
        [resource.inferred.id for resource in resources[:5]]
        + (["..."] if len(resources) > 5 else [])
    )
    raise ValueError(
        "Could not resolve that input to a known resource id. "
        f"Expected one of: {known_ids or '(no resources)'}."
    )
