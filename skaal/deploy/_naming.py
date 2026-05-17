"""Shared naming helpers for deploy-time artifacts and env-var keys."""

from __future__ import annotations

import hashlib

from skaal.binding.model import PlannedResource


def resource_slug(resource: PlannedResource) -> str:
    """Return a filesystem-safe slug for a bound resource."""
    bare = resource.inferred.source.bare_name or "resource"
    digest = hashlib.sha256(resource.inferred.id.encode("utf-8")).hexdigest()[:8]
    safe = "".join(c if c.isalnum() or c in {"-", "_"} else "_" for c in bare)
    return f"{safe}-{digest}"


def resource_slug_key(resource: PlannedResource) -> str:
    """Return the upper-case env-var token derived from `resource_slug`."""
    return resource_slug(resource).replace("-", "_").upper()


__all__ = ["resource_slug", "resource_slug_key"]
