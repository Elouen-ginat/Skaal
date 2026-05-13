"""skaal.inference — walk an `App` into a deterministic `InferredPlan`.

This package is the contract between the user-facing primitives and every
later phase of the redesign: the binding layer (Phase 3) consumes
`InferredPlan`, the runtime/deploy layer (Phase 4) consumes the `BoundPlan`
derived from it, and the plan-diff CLI (Phase 6) compares two fingerprints.

See ADR 028 §6.2 and ADR 030 for the design.
"""

from __future__ import annotations

from skaal.inference.fingerprint import fingerprint_plan, fingerprint_resource
from skaal.inference.model import (
    Edge,
    EdgeKind,
    InferredPlan,
    InferredResource,
    ResourceKind,
    ResourceOverrides,
    SchemaRef,
    SourceLocation,
)
from skaal.inference.walk import infer

__all__ = [
    "Edge",
    "EdgeKind",
    "InferredPlan",
    "InferredResource",
    "ResourceKind",
    "ResourceOverrides",
    "SchemaRef",
    "SourceLocation",
    "fingerprint_plan",
    "fingerprint_resource",
    "infer",
]
