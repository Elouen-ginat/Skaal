"""Typed source-to-resource map emitted by `skaal map`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from skaal.binding.model import BoundPlan, BoundResource
from skaal.inference.model import ResourceKind


def _resource_sort_key(entry: ResourceMapEntry) -> tuple[str, int, str, str]:
    """Return the deterministic file → line → symbol → id ordering.

    This keeps nearby declarations grouped together in both the CLI tree and
    the emitted JSON while still producing a total ordering for same-line or
    duplicate-name edge cases.
    """
    return (entry.file, entry.line, entry.qualname, entry.resource_id)


class ResourceMapEntry(BaseModel):
    """One source symbol mapped to one bound resource."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resource_id: str
    module: str
    qualname: str
    file: str
    line: int
    kind: ResourceKind
    backend: str
    region: str | None = None
    external: bool = False
    pinned: bool = False

    @classmethod
    def for_resource(cls, resource: BoundResource) -> ResourceMapEntry:
        """Build an entry from a bound resource."""
        source = resource.inferred.source
        return cls(
            resource_id=resource.inferred.id,
            module=source.module,
            qualname=source.qualname,
            file=source.file,
            line=source.line,
            kind=resource.inferred.kind,
            backend=resource.backend,
            region=resource.region,
            external=resource.external,
            pinned=resource.pinned,
        )


class ResourceMap(BaseModel):
    """The full source-to-resource map for one app/environment pair."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    app: str
    environment: str
    app_fingerprint: str
    bound_fingerprint: str
    resources: tuple[ResourceMapEntry, ...] = ()

    @classmethod
    def for_bound_plan(cls, bound: BoundPlan) -> ResourceMap:
        """Build the resource map from a bound plan."""
        entries = [ResourceMapEntry.for_resource(resource) for resource in bound.resources]
        resources = tuple(sorted(entries, key=_resource_sort_key))
        return cls(
            app=bound.app,
            environment=bound.environment,
            app_fingerprint=bound.app_fingerprint,
            bound_fingerprint=bound.bound_fingerprint,
            resources=resources,
        )

    def to_json(self) -> str:
        """Render the canonical JSON form for on-disk storage."""
        return self.model_dump_json(indent=2) + "\n"
