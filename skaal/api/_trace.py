"""Resolve resource ids and log lines back to inferred source locations."""

from __future__ import annotations

from dataclasses import dataclass

from skaal.binding.model import Plan, PlannedResource


@dataclass(frozen=True)
class SourceMatch:
    """One resolved trace result."""

    resource: PlannedResource
    matched_text: str


def resolve_trace(needle: str, bound: Plan) -> SourceMatch:
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
    for resource in resources:
        if needle == resource.inferred.id:
            return SourceMatch(resource=resource, matched_text=resource.inferred.id)

    matches = [resource for resource in resources if resource.inferred.id in needle]
    best_match: PlannedResource | None = (
        max(matches, key=lambda resource: len(resource.inferred.id)) if matches else None
    )
    if best_match is not None:
        return SourceMatch(resource=best_match, matched_text=best_match.inferred.id)

    known_ids = ", ".join(
        [resource.inferred.id for resource in resources[:5]]
        + (["..."] if len(resources) > 5 else [])
    )
    raise ValueError(
        "Could not resolve that input to a known resource id. "
        f"Expected one of: {known_ids or '(no resources)'}."
    )
