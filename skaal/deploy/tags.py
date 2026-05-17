"""Cloud-resource tagging helper (ADR 028 §6.11, ADR 032 §Decision 5).

Every Pulumi resource that `skaal.deploy.<target>` emits is tagged through
this one helper. The result is a typed `SkaalTags` pydantic model; call
`tags.as_mapping()` to get the prefixed ``{"skaal:app": ...}`` form
Pulumi resource constructors expect.

Centralising the schema in `SkaalTags` means a single ADR-driven change
touches every backend synth function at once; tags are budget-constrained
on most cloud providers, and changing keys after the fact orphans the
resources that carried the old keys.
"""

from __future__ import annotations

from skaal.binding.model import Environment, PlannedResource
from skaal.deploy.models import SkaalTags


def tags_for(resource: PlannedResource, env: Environment, fingerprint: str) -> SkaalTags:
    """Return the canonical Skaal tag set for one cloud resource.

    The ``fingerprint`` argument is `BoundPlan.app_fingerprint` (or
    `.bound_fingerprint`) — passed in rather than read off the plan so
    synth callers can choose which fingerprint travels with the resource
    (the app fingerprint is stable across env reconfigurations; the bound
    fingerprint changes whenever a backend choice does).

    Args:
        resource: The bound resource the tags will attach to.
        env: The active environment.
        fingerprint: The plan fingerprint to embed in ``skaal:fingerprint``.

    Returns:
        A typed `SkaalTags` instance. Use ``tags.as_mapping()`` for the
        Pulumi-shape dict.
    """
    return SkaalTags.for_resource(resource, env, fingerprint)


__all__ = ["tags_for"]
