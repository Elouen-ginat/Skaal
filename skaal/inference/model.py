"""Pydantic models for the inference layer.

Every type in this module is a frozen pydantic `BaseModel` with
``extra="forbid"``. The set of fields is closed: unknown keys raise at
``model_validate`` time, mutation after construction raises at attribute
set, and JSON round-trips are byte-stable via ``model_dump_json(by_alias=True)``.

See ADR 028 §6.2 and ADR 030 §2.1 for the design.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from skaal.types.storage import SecondaryIndex


class ResourceKind(StrEnum):
    """The nine resource shapes the inference layer recognises.

    The list is closed; new kinds require an ADR.
    """

    STORE = "store"
    RELATIONAL = "relational"
    BLOB = "blob"
    CHANNEL = "channel"
    FUNCTION = "function"
    ASGI_SERVICE = "asgi_service"
    SCHEDULE = "schedule"
    JOB = "job"
    SECRET = "secret"


class EdgeKind(StrEnum):
    """The five edge shapes between resources in an `InferredPlan`.

    Edges are not emitted in Phase 2 (`InferredPlan.edges` is always empty
    until the bytecode-level call-graph walker lands in Phase 6).
    """

    READS = "reads"
    WRITES = "writes"
    PUBLISHES = "publishes"
    SUBSCRIBES = "subscribes"
    INVOKES = "invokes"


class SourceLocation(BaseModel):
    """Where in the user's source tree a resource was declared."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    module: str
    qualname: str
    file: str
    line: int

    @classmethod
    def from_object(cls, obj: object) -> SourceLocation:
        """Return the location ``obj`` was defined at, or an unknown placeholder."""
        module = getattr(obj, "__module__", "<unknown>") or "<unknown>"
        qualname = getattr(obj, "__qualname__", getattr(obj, "__name__", "<unknown>"))
        try:
            file = inspect.getsourcefile(obj) or "<unknown>"  # type: ignore[arg-type]
        except (TypeError, OSError):
            file = "<unknown>"
        try:
            _, line = inspect.getsourcelines(obj)  # type: ignore[arg-type]
        except (TypeError, OSError):
            line = 0
        return cls(module=module, qualname=qualname, file=file, line=line)


class SchemaRef(BaseModel):
    """Reference to the pydantic / SQLModel schema backing a resource."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_qualname: str
    fingerprint: str

    @classmethod
    def from_class(cls, target: type) -> SchemaRef | None:
        """Build a `SchemaRef` from a pydantic-shaped class, or return ``None``.

        The schema fingerprint is the first 16 hex chars of
        ``sha256(canonical_json(model_json_schema()))``. SQLModel classes are
        recognised via their ``__table__`` attribute and fall back to the
        pydantic ``model_json_schema()`` path.
        """
        if not isinstance(target, type):
            return None
        schema_fn = getattr(target, "model_json_schema", None)
        if not callable(schema_fn):
            return None
        try:
            schema = schema_fn()
        except Exception:
            return None
        canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        return cls(model_qualname=target.__qualname__, fingerprint=fingerprint)


class ResourceOverrides(BaseModel):
    """The full set of declaration-site knobs (ADR 028 §6.5).

    Phase 2 only populates ``backend`` indirectly (via the second generic
    parameter on the primitive class, when Phase 3 wires it up). The other
    fields are placeholders the binding layer reads in Phase 3.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: str | None = None
    region: str | None = None
    memory_mb: int | None = None
    timeout_s: float | None = None
    min_concurrency: int | None = None
    max_concurrency: int | None = None


class Edge(BaseModel):
    """A directed edge between two resources in an `InferredPlan`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    target_id: str
    kind: EdgeKind


class InferredResource(BaseModel):
    """A single resource discovered by walking an `App`.

    The ``id`` is the canonical ``<module>:<qualname>`` form used in
    ``[env.<name>.overrides]`` blocks of ``skaal.toml`` (ADR 028 §6.5).
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )

    id: str
    kind: ResourceKind
    source: SourceLocation
    schema_: SchemaRef | None = Field(default=None, alias="schema")
    indexes: tuple[SecondaryIndex, ...] = ()
    overrides: ResourceOverrides = ResourceOverrides()

    @staticmethod
    def id_for(obj: object) -> str:
        """Compute the canonical ``<module>:<qualname>`` identifier for ``obj``."""
        module = getattr(obj, "__module__", "<unknown>") or "<unknown>"
        qualname = getattr(obj, "__qualname__", getattr(obj, "__name__", repr(obj)))
        return f"{module}:{qualname}"


class InferredPlan(BaseModel):
    """The deterministic, environment-independent output of the inference walk.

    The fingerprint is computed by `skaal.inference.fingerprint.fingerprint_plan`
    after the resource tuple is finalised; callers should not construct this
    model directly with a hand-picked fingerprint outside of tests.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    app: str
    resources: tuple[InferredResource, ...] = ()
    edges: tuple[Edge, ...] = ()
    fingerprint: str = ""

    def with_fingerprint(self, fingerprint: str) -> InferredPlan:
        """Return a copy of this plan with ``fingerprint`` filled in.

        Used by the walker to finalise a plan whose resources are already
        sorted. The frozen-model contract prevents in-place mutation.
        """
        return self.model_copy(update={"fingerprint": fingerprint})


def _canonical_payload(plan: InferredPlan) -> bytes:
    """Return the byte-stable JSON form of a plan, excluding its fingerprint.

    This is the exact payload the fingerprint hashes over. Exposed here (not in
    `fingerprint.py`) so model-layer tests can assert on it directly.
    """
    data = plan.model_dump(mode="json", by_alias=True, exclude={"fingerprint"})
    data["resources"] = sorted(
        data["resources"], key=lambda r: (r["kind"], r["id"])
    )
    data["edges"] = sorted(
        data["edges"], key=lambda e: (e["source_id"], e["target_id"], e["kind"])
    )
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _canonical_resource_payload(res: InferredResource) -> bytes:
    """Byte-stable JSON form of a single resource."""
    data: dict[str, Any] = res.model_dump(mode="json", by_alias=True)
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
