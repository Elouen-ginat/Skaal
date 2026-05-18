"""Adapter for `BLOB` resources."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skaal.errors import RuntimeAdapterMissing
from skaal.runtime._registry import RuntimeBackendFactoryContext, get_runtime_target

if TYPE_CHECKING:
    from skaal.binding.model import PlannedResource
    from skaal.runtime.local.runtime import LocalRuntime


def register(runtime: LocalRuntime, bound: PlannedResource, target: Any) -> None:
    if target is None or bound.external:
        return
    from collections.abc import Callable

    local_target = get_runtime_target("local")
    if not local_target.has_backend_factory(bound.inferred.kind, bound.backend):
        raise RuntimeAdapterMissing(f"blob/{bound.backend}")

    backend: Any = local_target.build_backend(
        RuntimeBackendFactoryContext(
            target_name="local",
            resource_kind=bound.inferred.kind,
            backend_name=bound.backend,
            target=target,
            planned_resource=bound,
        )
    )
    wire: Callable[[Any], None] | None = getattr(target, "wire", None)
    if wire is not None:
        wire(backend)
