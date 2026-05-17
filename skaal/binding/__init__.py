"""The binding layer (ADR 028 §6.3, ADR 031).

Combines a `Blueprint` with an `Environment` and the `skaal.lock` file
to produce a `Plan` — every resource bound to exactly one concrete
backend by deterministic table lookup.

The public surface re-exports the pydantic models, the `plan` function,
and the registry/defaults helpers used by the runtime and deploy layers.
"""

from __future__ import annotations

from skaal.binding.bind import plan
from skaal.binding.defaults import DEFAULTS
from skaal.binding.model import (
    BackendConfig,
    Environment,
    EnvOverride,
    LockEntry,
    LockFile,
    Plan,
    PlannedResource,
    Target,
)
from skaal.binding.registry import (
    REGISTRY,
    BackendCapabilities,
    BackendSpec,
    lookup,
    lookup_token,
    tokens_for,
)

__all__ = [
    "DEFAULTS",
    "REGISTRY",
    "BackendCapabilities",
    "BackendConfig",
    "BackendSpec",
    "EnvOverride",
    "Environment",
    "LockEntry",
    "LockFile",
    "Plan",
    "PlannedResource",
    "Target",
    "lookup",
    "lookup_token",
    "plan",
    "tokens_for",
]
