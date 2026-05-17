"""The per-`(ResourceKind, Target)` defaults projection (ADR 028 §6.3, ADR 031 §3.5).

`DEFAULTS` is now derived from the backend registry's `BackendEntry.default_for`
metadata so binding defaults, backend capabilities/targets, and deploy-side
backend metadata stay in lock-step. The projection remains wrapped in
`MappingProxyType` so consumers keep the same read-only table shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from skaal.backends._base import Backend
from skaal.binding.model import Target
from skaal.binding.registry import REGISTRY
from skaal.inference.model import ResourceKind


def _build_defaults() -> Mapping[ResourceKind, Mapping[Target, type[Backend[Any]]]]:
    rows: dict[ResourceKind, dict[Target, type[Backend[Any]]]] = {kind: {} for kind in ResourceKind}
    for entry in REGISTRY:
        for default in entry.default_for:
            rows[default.kind][default.target] = entry.token_class
    return MappingProxyType(
        {
            kind: MappingProxyType({target: rows[kind][target] for target in Target})
            for kind in ResourceKind
        }
    )


DEFAULTS: Mapping[ResourceKind, Mapping[Target, type[Backend[Any]]]] = _build_defaults()
