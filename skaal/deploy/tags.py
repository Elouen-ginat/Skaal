"""Cloud-resource tagging helper (ADR 028 §6.11, ADR 032 §Decision 5).

Every Pulumi resource that `skaal.deploy.<target>` emits is tagged through
this one helper. Centralising the schema here means a single ADR-driven
change touches every backend synth function at once.

The tag set is intentionally short and stable; tags are budget-constrained
on most cloud providers, and changing tag keys after the fact orphans the
resources that carried the old keys.
"""

from __future__ import annotations

from collections.abc import Mapping

from skaal.binding.model import BoundResource, Environment


def tags_for(
    resource: BoundResource,
    env: Environment,
    fingerprint: str,
) -> Mapping[str, str]:
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
        A mapping of tag keys to string values. The mapping is fresh per
        call so callers can mutate / extend without aliasing.
    """
    inferred = resource.inferred
    return {
        "skaal:app": inferred.source.top_package,
        "skaal:resource_id": inferred.id,
        "skaal:kind": inferred.kind.value,
        "skaal:env": env.name,
        "skaal:target": env.target.value,
        "skaal:backend": resource.backend,
        "skaal:fingerprint": fingerprint,
    }


__all__ = ["tags_for"]
