"""Per-kind adapter dispatch for the local runtime."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from skaal.inference.model import ResourceKind
from skaal.runtime._registry import get_runtime_target

if TYPE_CHECKING:
    from skaal.binding.model import PlannedResource
    from skaal.runtime.local.runtime import LocalRuntime


AdapterFn = Callable[["LocalRuntime", "PlannedResource", Any], None]


LOCAL_DISPATCH: dict[ResourceKind, AdapterFn] = get_runtime_target("local").kind_adapters


def dispatch_for(kind: ResourceKind) -> AdapterFn:
    return get_runtime_target("local").adapter_for(kind)
