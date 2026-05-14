"""The binding layer (ADR 028 §6.3, ADR 031).

Combines an `InferredPlan` with an `Environment` and the `skaal.lock` file
to produce a `BoundPlan` — every resource bound to exactly one concrete
backend by deterministic table lookup.

The public surface re-exports the pydantic models, the `bind` function,
and the TOML loaders/writers; the registry and defaults table are
framework-internal but available for tests and the Phase 4 deploy layer.
"""

from __future__ import annotations

from skaal.binding.bind import bind
from skaal.binding.defaults import DEFAULTS
from skaal.binding.environment import load_environment, load_environments
from skaal.binding.lock import load_lock, write_lock
from skaal.binding.model import (
    BackendConfig,
    BoundPlan,
    BoundResource,
    Environment,
    LockEntry,
    LockFile,
    ResourceOverride,
    Target,
)
from skaal.binding.registry import (
    REGISTRY,
    BackendCapabilities,
    BackendEntry,
    lookup,
    lookup_token,
    tokens_for,
)

__all__ = [
    "DEFAULTS",
    "REGISTRY",
    "BackendCapabilities",
    "BackendConfig",
    "BackendEntry",
    "BoundPlan",
    "BoundResource",
    "Environment",
    "LockEntry",
    "LockFile",
    "ResourceOverride",
    "Target",
    "bind",
    "load_environment",
    "load_environments",
    "load_lock",
    "lookup",
    "lookup_token",
    "tokens_for",
    "write_lock",
]
