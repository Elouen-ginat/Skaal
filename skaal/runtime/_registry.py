"""Runtime-target registry for local and deploy-managed bootstrap layers.

The deploy registry maps `Target` enums to synth containers. The
runtime side needs a parallel seam so built-in code and plugins can
contribute:

- local per-kind adapters (used by `LocalRuntime.from_bound_plan(...)`)
- cold-start binding wirers (used by deploy-managed runtimes like AWS)
- backend factories keyed by `(ResourceKind, backend_name)`

The registry is intentionally small and runtime-only. Target-owned entry
points such as `skaal.runtime.local.dispatch.dispatch_for(...)` and
`skaal.runtime.aws.wire_app_from_environment(...)` delegate into this
layer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING, Any

from skaal.errors import RuntimeAdapterMissing, RuntimeWiringError, SkaalConfigError

if TYPE_CHECKING:
    from skaal.binding.model import PlannedResource
    from skaal.inference.model import ResourceKind
    from skaal.runtime.models import RuntimeResourceBinding


RuntimeAdapterFn = Callable[[Any, "PlannedResource", Any], None]


@dataclass(frozen=True)
class RuntimeBackendFactoryContext:
    """All inputs a runtime backend factory or wirer may need."""

    target_name: str
    resource_kind: ResourceKind
    backend_name: str
    target: Any
    planned_resource: PlannedResource | None = None
    binding: RuntimeResourceBinding | None = None
    env: Mapping[str, str] | None = None


RuntimeBackendFactoryFn = Callable[[RuntimeBackendFactoryContext], Any]
RuntimeBindingWiringFn = Callable[[RuntimeBackendFactoryContext], None]


@dataclass
class RuntimeTargetRegistration:
    """Mutable registration bucket for one runtime target."""

    name: str
    kind_adapters: dict[ResourceKind, RuntimeAdapterFn] = field(default_factory=dict)
    binding_wirers: dict[ResourceKind, RuntimeBindingWiringFn] = field(default_factory=dict)
    backend_factories: dict[tuple[ResourceKind, str], RuntimeBackendFactoryFn] = field(
        default_factory=dict
    )
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def register_adapter(self, kind: ResourceKind, adapter: RuntimeAdapterFn) -> None:
        with self._lock:
            self.kind_adapters[kind] = adapter

    def adapter_for(self, kind: ResourceKind) -> RuntimeAdapterFn:
        adapter = self.kind_adapters.get(kind)
        if adapter is None:
            raise RuntimeAdapterMissing(kind.value)
        return adapter

    def register_binding_wirer(self, kind: ResourceKind, wirer: RuntimeBindingWiringFn) -> None:
        with self._lock:
            self.binding_wirers[kind] = wirer

    def binding_wirer_for(self, kind: ResourceKind) -> RuntimeBindingWiringFn:
        wirer = self.binding_wirers.get(kind)
        if wirer is None:
            raise RuntimeWiringError(
                f"Runtime target {self.name!r} has no binding wirer for {kind.value!r}."
            )
        return wirer

    def wire_binding(self, context: RuntimeBackendFactoryContext) -> None:
        self.binding_wirer_for(context.resource_kind)(context)

    def register_backend_factory(
        self,
        kind: ResourceKind,
        backend_name: str,
        factory: RuntimeBackendFactoryFn,
    ) -> None:
        with self._lock:
            self.backend_factories[(kind, backend_name)] = factory

    def has_backend_factory(self, kind: ResourceKind, backend_name: str) -> bool:
        return (kind, backend_name) in self.backend_factories

    def build_backend(self, context: RuntimeBackendFactoryContext) -> Any:
        factory = self.backend_factories.get((context.resource_kind, context.backend_name))
        if factory is None:
            raise RuntimeWiringError(
                "No runtime backend factory registered for "
                f"target {self.name!r} and "
                f"{context.resource_kind.value}/{context.backend_name}."
            )
        return factory(context)


_TARGETS: dict[str, RuntimeTargetRegistration] = {}
_LOCK = Lock()


def register_runtime_target(target: RuntimeTargetRegistration) -> None:
    """Register or replace a runtime target by name."""
    with _LOCK:
        _TARGETS[target.name] = target


def get_runtime_target(name: str) -> RuntimeTargetRegistration:
    """Return the registered runtime target or raise a config error."""
    _ensure_builtin_targets_loaded()
    _ensure_plugins_loaded()
    target = _TARGETS.get(name)
    if target is None:
        registered = ", ".join(sorted(_TARGETS)) or "(none)"
        raise SkaalConfigError(
            f"No runtime target registered for {name!r}. Registered runtime targets: {registered}."
        )
    return target


def registered_runtime_targets() -> Mapping[str, RuntimeTargetRegistration]:
    """Return a snapshot of every registered runtime target."""
    _ensure_builtin_targets_loaded()
    _ensure_plugins_loaded()
    with _LOCK:
        return dict(_TARGETS)


def _ensure_builtin_targets_loaded() -> None:
    from skaal.runtime.aws.target import register_builtin_runtime_target as register_aws
    from skaal.runtime.local.target import register_builtin_runtime_target as register_local

    register_local()
    register_aws()


def _ensure_plugins_loaded() -> None:
    from skaal.plugins import load_plugins

    load_plugins()


def _reset_for_tests() -> None:
    with _LOCK:
        _TARGETS.clear()


__all__ = [
    "RuntimeAdapterFn",
    "RuntimeBackendFactoryContext",
    "RuntimeBackendFactoryFn",
    "RuntimeBindingWiringFn",
    "RuntimeTargetRegistration",
    "get_runtime_target",
    "register_runtime_target",
    "registered_runtime_targets",
]
