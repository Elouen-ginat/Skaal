"""Adapter for `RELATIONAL` resources."""

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
    from skaal.table import wire_relational_model

    local_target = get_runtime_target("local")
    if not local_target.has_backend_factory(bound.inferred.kind, bound.backend):
        raise RuntimeAdapterMissing(f"relational/{bound.backend}")

    backend: Any = local_target.build_backend(
        RuntimeBackendFactoryContext(
            target_name="local",
            resource_kind=bound.inferred.kind,
            backend_name=bound.backend,
            target=target,
            planned_resource=bound,
        )
    )

    async def _startup() -> None:
        connect = getattr(backend, "connect", None)
        if connect is not None:
            await connect()

    async def _shutdown() -> None:
        close = getattr(backend, "close", None)
        if close is not None:
            await close()

    wire_relational_model(target, backend)
    runtime.state.relational_backends[target.__name__] = backend
    runtime.add_startup_hook(_startup)
    runtime.add_shutdown_hook(_shutdown)
