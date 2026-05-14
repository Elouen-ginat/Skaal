"""Module — reusable, composable Skaal fragment. Base class for App.

The agent / pattern surface and the constraint vocabulary
(`Latency`, `Throughput`, `Durability`, `AccessPattern`,
`Compute`, `Scale`, `DecommissionPolicy`) have been removed per ADR 028
Phase 1. Decorators retain only their structural arguments; the inference
layer (Phase 2) re-derives infrastructure shape from class shape, not
constraints.

Phase 4 (ADR 032 §4.9) deletes every legacy per-decorator dunder
(`storage`, `function`, `schedule`, `channel`, `job`, `secrets`);
``__skaal_inferred__`` is the single contract decorated objects expose.
"""

from __future__ import annotations

import weakref
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast, overload

from skaal.inference.model import (
    InferredResource,
    ResourceKind,
    ResourceOverrides,
    SchemaRef,
    SourceLocation,
)
from skaal.inference.runtime_meta import encode_resilience, encode_trigger
from skaal.types import (
    BeforeInvoke,
    Bulkhead,
    CircuitBreaker,
    Duration,
    JobHandle,
    RateLimitPolicy,
    RetryPolicy,
    SecondaryIndex,
    SecretRef,
)
from skaal.types.invoke import AuthClaims
from skaal.types.protocols import AsyncPublishTarget

if TYPE_CHECKING:
    from skaal.channel import Channel
    from skaal.schedule import Cron, Every

F = TypeVar("F", bound=Callable[..., Any])
C = TypeVar("C", bound=type)
ChannelT = TypeVar("ChannelT", bound="Channel[Any]")
StorageKind = Literal["kv", "blob", "relational"]


class ModuleExport:
    """Typed handle for symbols exported by a `Module`."""

    def __init__(
        self,
        storage: dict[str, Any],
        functions: dict[str, Any],
        channels: dict[str, Any],
        namespace: str,
    ) -> None:
        self.storage = storage
        self.functions = functions
        self.channels = channels
        self.namespace = namespace

    def __repr__(self) -> str:
        return (
            f"ModuleExport(namespace={self.namespace!r}, "
            f"storage={list(self.storage)}, "
            f"functions={list(self.functions)})"
        )


@dataclass(slots=True)
class _BeforeInvokeContext:
    function_name: str
    kwargs: dict[str, Any]
    is_stream: bool
    attempt: int
    headers: Mapping[str, str]
    auth_claims: AuthClaims | None
    auth_subject: str | None
    trace_id: str | None
    span_id: str | None


class _HasDunderName:
    __name__: str


def _attach_inferred(target: Any, inferred: InferredResource) -> None:
    """Attach the inference-layer `InferredResource` to a decorated object.

    `__skaal_inferred__` is the single contract every consumer (runtime,
    deploy, `_resolve_invokable`, the kind-detection predicates) reads
    after the Phase 4 dunder sweep.
    """
    import contextlib

    with contextlib.suppress(AttributeError, TypeError):  # slotted-but-unwritable objects
        target.__skaal_inferred__ = inferred


def _inferred_kind(obj: Any) -> ResourceKind | None:
    """Return the `ResourceKind` recorded on ``obj`` by `_attach_inferred`."""
    inferred = getattr(obj, "__skaal_inferred__", None)
    if isinstance(inferred, InferredResource):
        return inferred.kind
    return None


class Module:
    """A reusable, composable Skaal fragment.

    A `Module` can declare storage classes, functions, jobs, channels, and
    schedules. It has no deploy target; modules are mounted into apps (or
    other modules) via `app.use(module)` which namespaces their resources.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._storage: dict[str, Any] = {}
        self._functions: dict[str, Any] = {}
        self._jobs: dict[str, Any] = {}
        self._channels: dict[str, Channel[Any]] = {}
        self._components: dict[str, Any] = {}
        self._schedules: dict[str, Any] = {}
        self._secrets: dict[str, SecretRef] = {}
        self._exports: set[str] = set()
        self._submodules: dict[str, Module] = {}
        self._before_invoke: list[BeforeInvoke] = []
        self._runtime_ref: weakref.ReferenceType[Any] | None = None

    # ── Registration decorators ────────────────────────────────────────────

    @overload
    def storage(
        self,
        cls_to_decorate: C,
        *,
        kind: StorageKind | str = ...,
        indexes: list[SecondaryIndex] | None = ...,
    ) -> C: ...

    @overload
    def storage(
        self,
        cls_to_decorate: None = ...,
        *,
        kind: StorageKind | str = ...,
        indexes: list[SecondaryIndex] | None = ...,
    ) -> Callable[[C], C]: ...

    def storage(
        self,
        cls_to_decorate: C | None = None,
        *,
        kind: StorageKind | str = "kv",
        indexes: list[SecondaryIndex] | None = None,
    ) -> C | Callable[[C], C]:
        """Register a storage class with this module."""
        from skaal.decorators import storage as _storage_dec

        storage_decorator = cast(Callable[..., Any], _storage_dec)
        outer = storage_decorator(kind=kind, indexes=indexes)

        def decorator(cls: C) -> C:
            annotated = outer(cls)
            self._storage[cls.__name__] = annotated
            return annotated

        if cls_to_decorate is None:
            return decorator
        return decorator(cls_to_decorate)

    def external(
        self,
        *,
        name: str,
        kind: StorageKind | str = "kv",
    ) -> Callable[[C], C]:
        """Register an externally-provisioned, type-pinned storage class.

        See `skaal.decorators.external` for the contract: the decorated
        class must declare a `Backend` type-pin via its second generic
        parameter; ``name`` indexes into ``[env.<name>.backends]`` in
        `skaal.toml` for the connection string.
        """
        from skaal.decorators import external as _external_dec

        outer = _external_dec(name=name, kind=kind)

        def decorator(cls: C) -> C:
            annotated = outer(cls)
            self._storage[cls.__name__] = annotated
            return annotated

        return decorator

    @overload
    def function(
        self,
        fn_to_decorate: F,
        *,
        retry: RetryPolicy | None = ...,
        circuit_breaker: CircuitBreaker | None = ...,
        rate_limit: RateLimitPolicy | None = ...,
        bulkhead: Bulkhead | None = ...,
        secrets: list[SecretRef] | None = ...,
    ) -> F: ...

    @overload
    def function(
        self,
        fn_to_decorate: None = ...,
        *,
        retry: RetryPolicy | None = ...,
        circuit_breaker: CircuitBreaker | None = ...,
        rate_limit: RateLimitPolicy | None = ...,
        bulkhead: Bulkhead | None = ...,
        secrets: list[SecretRef] | None = ...,
    ) -> Callable[[F], F]: ...

    def function(
        self,
        fn_to_decorate: F | None = None,
        *,
        retry: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        rate_limit: RateLimitPolicy | None = None,
        bulkhead: Bulkhead | None = None,
        secrets: list[SecretRef] | None = None,
    ) -> F | Callable[[F], F]:
        """Register a function with optional resilience policies."""

        def decorator(fn: F) -> F:
            overrides = ResourceOverrides(
                resilience=encode_resilience(
                    retry=retry,
                    circuit_breaker=circuit_breaker,
                    rate_limit=rate_limit,
                    bulkhead=bulkhead,
                ),
            )
            _attach_inferred(
                fn,
                InferredResource(
                    id=InferredResource.id_for(fn),
                    kind=ResourceKind.FUNCTION,
                    source=SourceLocation.from_object(fn),
                    overrides=overrides,
                ),
            )
            if secrets:
                for ref in secrets:
                    self.secret(ref)
            self._functions[fn.__name__] = fn
            return fn

        if fn_to_decorate is None:
            return decorator
        return decorator(fn_to_decorate)

    @overload
    def job(
        self,
        fn_to_decorate: F,
        *,
        retry: RetryPolicy | None = ...,
    ) -> F: ...

    @overload
    def job(
        self,
        fn_to_decorate: None = ...,
        *,
        retry: RetryPolicy | None = ...,
    ) -> Callable[[F], F]: ...

    def job(
        self,
        fn_to_decorate: F | None = None,
        *,
        retry: RetryPolicy | None = None,
    ) -> F | Callable[[F], F]:
        """Register a background job handler executed by the runtime worker."""

        def decorator(fn: F) -> F:
            overrides = ResourceOverrides(
                resilience=encode_resilience(
                    retry=retry,
                    circuit_breaker=None,
                    rate_limit=None,
                    bulkhead=None,
                ),
            )
            _attach_inferred(
                fn,
                InferredResource(
                    id=InferredResource.id_for(fn),
                    kind=ResourceKind.JOB,
                    source=SourceLocation.from_object(fn),
                    overrides=overrides,
                ),
            )
            self._jobs[fn.__name__] = fn
            return fn

        if fn_to_decorate is None:
            return decorator
        return decorator(fn_to_decorate)

    async def enqueue(
        self,
        job: str | Callable[..., Any],
        *args: Any,
        delay: Duration | str | None = None,
        run_at: datetime | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> JobHandle:
        """Queue a registered background job on the active runtime."""
        job_name, _ = self._resolve_job(job)
        runtime = self._require_runtime()
        return await runtime.enqueue_job(
            job_name,
            *args,
            delay=delay,
            run_at=run_at,
            idempotency_key=idempotency_key,
            **kwargs,
        )

    def channel(
        self,
        *,
        buffer: int = 1000,
    ) -> Callable[[C], C]:
        """Register a `Channel` subclass as a named resource on this module."""

        def decorator(cls: C) -> C:
            from skaal.decorators import _extract_backend_pin

            instance = cls(buffer=buffer)
            pinned_token = _extract_backend_pin(cls)
            overrides = ResourceOverrides(
                backend=pinned_token.name if pinned_token is not None else None,
                channel_buffer=buffer,
            )
            inferred = InferredResource(
                id=InferredResource.id_for(cls),
                kind=ResourceKind.CHANNEL,
                source=SourceLocation.from_object(cls),
                schema_=SchemaRef.from_class(cls),
                overrides=overrides,
            )
            _attach_inferred(cls, inferred)
            _attach_inferred(instance, inferred)
            self._channels[cls.__name__] = instance
            return cls

        return decorator

    def attach(self, component: Any) -> Any:
        """Attach an external component to this module."""
        from skaal.components import ExternalComponent

        self._components[component.name] = component
        if isinstance(component, ExternalComponent) and component.secret is not None:
            self.secret(component.secret)
        return component

    def get_channel(self, channel_cls: type[ChannelT]) -> ChannelT:
        """Return the registered channel instance for a decorated `Channel` subclass."""
        channel = self._channels.get(channel_cls.__name__)
        if channel is None:
            raise KeyError(
                f"Channel {channel_cls.__name__!r} is not registered with module {self.name!r}"
            )
        if not isinstance(channel, channel_cls):
            raise TypeError(
                f"Registered channel {channel_cls.__name__!r} is "
                f"{type(channel).__name__}, expected {channel_cls.__name__}"
            )
        return channel

    def secret(self, ref: SecretRef) -> SecretRef:
        """Declare a secret consumed by this module's functions."""
        existing = self._secrets.get(ref.name)
        if existing is not None and existing != ref:
            raise ValueError(
                f"Secret {ref.name!r} re-declared with different parameters: {existing} vs {ref}"
            )
        self._secrets[ref.name] = ref
        return ref

    @overload
    def schedule(
        self,
        fn_to_decorate: F,
        *,
        trigger: Every | Cron,
        emit_to: AsyncPublishTarget[object] | None = ...,
        timezone: str = ...,
    ) -> F: ...

    @overload
    def schedule(
        self,
        fn_to_decorate: None = ...,
        *,
        trigger: Every | Cron,
        emit_to: AsyncPublishTarget[object] | None = ...,
        timezone: str = ...,
    ) -> Callable[[F], F]: ...

    def schedule(
        self,
        fn_to_decorate: F | None = None,
        *,
        trigger: Every | Cron,
        emit_to: AsyncPublishTarget[object] | None = None,
        timezone: str = "UTC",
    ) -> F | Callable[[F], F]:
        """Register a background function triggered on a time-based schedule."""

        def decorator(fn: F) -> F:
            overrides = ResourceOverrides(
                trigger=encode_trigger(trigger),
                schedule_timezone=timezone,
            )
            _attach_inferred(
                fn,
                InferredResource(
                    id=InferredResource.id_for(fn),
                    kind=ResourceKind.SCHEDULE,
                    source=SourceLocation.from_object(fn),
                    overrides=overrides,
                ),
            )
            self._schedules[fn.__name__] = fn
            # `emit_to` is accepted but not yet honoured by the new
            # local-runtime SCHEDULE adapter; it will be wired in alongside
            # the deploy-side EventBridge / Cloud Scheduler synth.
            _ = emit_to
            return fn

        if fn_to_decorate is None:
            return decorator
        return decorator(fn_to_decorate)

    def add_before_invoke(self, hook: BeforeInvoke) -> BeforeInvoke:
        """Register a hook that runs before every resilience-wrapped invocation."""
        self._before_invoke.append(hook)
        return hook

    async def invoke(self, fn: str | Callable[..., Any], **kwargs: Any) -> Any:
        """Invoke a registered function through the active runtime's resilience stack."""
        function_name, _ = self._resolve_invokable(fn)
        runtime = self._require_runtime()
        return await runtime.invoke(function_name, kwargs)

    def invoke_stream(self, fn: str | Callable[..., Any], **kwargs: Any) -> AsyncIterator[Any]:
        """Invoke a registered async iterator function through the active runtime."""
        function_name, _ = self._resolve_invokable(fn)
        runtime = self._require_runtime()
        return runtime.invoke_stream(function_name, kwargs)

    # ── Export / import API ────────────────────────────────────────────────

    def export(self, *symbols: Any) -> ModuleExport:
        """Mark symbols as importable by mounting apps."""
        registered: dict[str, dict[str, Any]] = {
            "storage": self._storage,
            "functions": self._functions,
            "channels": self._channels,
        }

        exp_storage: dict[str, Any] = {}
        exp_functions: dict[str, Any] = {}
        exp_channels: dict[str, Any] = {}

        for sym in symbols:
            sym_name = _symbol_export_name(sym)
            found = False
            for bucket_name, bucket in registered.items():
                if sym_name in bucket:
                    self._exports.add(sym_name)
                    found = True
                    if bucket_name == "storage":
                        exp_storage[sym_name] = sym
                    elif bucket_name == "functions":
                        exp_functions[sym_name] = sym
                    elif bucket_name == "channels":
                        exp_channels[sym_name] = sym
                    break
            if not found:
                raise ValueError(
                    f"{sym_name!r} is not registered with module {self.name!r}. "
                    f"Register it with @{self.name}.storage / .function / .channel first."
                )

        return ModuleExport(
            storage=exp_storage,
            functions=exp_functions,
            channels=exp_channels,
            namespace=self.name,
        )

    def use(
        self,
        module: Module,
        *,
        namespace: str | None = None,
        share_storage: list[str] | None = None,
    ) -> ModuleExport:
        """Mount a `Module` into this `Module`, namespacing its resources."""
        ns = namespace if namespace is not None else module.name
        if ns in self._submodules:
            raise ValueError(
                f"Namespace {ns!r} is already occupied by another module. "
                "Pass a different namespace= to app.use()."
            )
        if ns is not None:
            self._submodules[ns] = module
        else:
            for bucket in (self._storage, self._functions, self._channels):
                for key in module._exports:
                    if key in bucket:
                        raise ValueError(
                            f"Cannot merge module {module.name!r} into root namespace: "
                            f"{key!r} already registered. Use namespace=<name> instead."
                        )
            self._submodules[""] = module

        exp_storage = {k: v for k, v in module._storage.items() if k in module._exports}
        exp_functions = {k: v for k, v in module._functions.items() if k in module._exports}
        exp_channels = {k: v for k, v in module._channels.items() if k in module._exports}

        return ModuleExport(
            storage=exp_storage,
            functions=exp_functions,
            channels=exp_channels,
            namespace=ns or "",
        )

    # ── Inference-graph collection ─────────────────────────────────────────

    def _collect_all(self) -> dict[str, Any]:
        """Recursively collect all registered resources from this module and submodules."""
        result: dict[str, Any] = {}
        prefix = f"{self.name}." if self.name else ""

        for name, obj in self._storage.items():
            result[f"{prefix}{name}"] = obj
        for name, obj in self._functions.items():
            result[f"{prefix}{name}"] = obj
        for name, obj in self._jobs.items():
            result[f"{prefix}{name}"] = obj
        for name, obj in self._channels.items():
            result[f"{prefix}{name}"] = obj
        for name, obj in self._schedules.items():
            result[f"{prefix}{name}"] = obj

        for ns, sub in self._submodules.items():
            sub_prefix = f"{prefix}{ns}." if ns else prefix
            for qname, obj in sub._collect_all().items():
                bare = qname[len(sub.name) + 1 :] if qname.startswith(sub.name + ".") else qname

                sym_name = bare.split(".")[-1]
                if sym_name not in sub._exports and ns:
                    continue

                result[f"{sub_prefix}{bare}"] = obj

        return result

    def _collect_secrets(self) -> dict[str, SecretRef]:
        """Recursively collect declared secrets from this module and submodules."""
        out: dict[str, SecretRef] = {}

        def _merge(src: dict[str, SecretRef]) -> None:
            for name, ref in src.items():
                existing = out.get(name)
                if existing is not None and existing != ref:
                    raise ValueError(
                        f"Secret {name!r} re-declared with different parameters: "
                        f"{existing} vs {ref}"
                    )
                out[name] = ref

        _merge(self._secrets)
        for sub in self._submodules.values():
            _merge(sub._collect_secrets())
        return out

    def _collect_jobs(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        prefix = f"{self.name}." if self.name else ""

        for name, obj in self._jobs.items():
            result[f"{prefix}{name}"] = obj

        for ns, sub in self._submodules.items():
            sub_prefix = f"{prefix}{ns}." if ns else prefix
            for qname, obj in sub._collect_jobs().items():
                bare = qname[len(sub.name) + 1 :] if qname.startswith(sub.name + ".") else qname
                result[f"{sub_prefix}{bare}"] = obj

        return result

    def _bind_runtime(self, runtime: Any) -> None:
        self._runtime_ref = weakref.ref(runtime)
        for submodule in self._submodules.values():
            submodule._bind_runtime(runtime)

    def _unbind_runtime(self, runtime: Any) -> None:
        if self._runtime_ref is not None and self._runtime_ref() is runtime:
            self._runtime_ref = None
        for submodule in self._submodules.values():
            submodule._unbind_runtime(runtime)

    def _require_runtime(self) -> Any:
        runtime = self._runtime_ref() if self._runtime_ref is not None else None
        if runtime is None:
            raise RuntimeError(
                "No active Skaal runtime is bound to this app. "
                "Start or construct a runtime before calling app.invoke(...)."
            )
        return runtime

    async def _prepare_invoke_kwargs(
        self,
        function_name: str,
        kwargs: dict[str, Any],
        *,
        is_stream: bool,
        attempt: int,
        headers: Mapping[str, str] | None = None,
        auth_claims: Mapping[str, Any] | None = None,
        auth_subject: str | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> dict[str, Any]:
        ctx = _BeforeInvokeContext(
            function_name=function_name,
            kwargs=dict(kwargs),
            is_stream=is_stream,
            attempt=attempt,
            headers=dict(headers or {}),
            auth_claims=cast(AuthClaims | None, dict(auth_claims or {}) or None),
            auth_subject=auth_subject,
            trace_id=trace_id,
            span_id=span_id,
        )
        for hook in self._before_invoke:
            await hook(ctx)
        return ctx.kwargs

    def _resolve_invokable(self, fn: str | Callable[..., Any]) -> tuple[str, Callable[..., Any]]:
        invokable_kinds = {ResourceKind.FUNCTION, ResourceKind.SCHEDULE}
        invokables = {
            name: obj
            for name, obj in self._collect_all().items()
            if callable(obj) and _inferred_kind(obj) in invokable_kinds
        }

        if isinstance(fn, str):
            direct = invokables.get(fn)
            if direct is not None:
                return fn, direct
            for function_name, obj in invokables.items():
                if _callable_name(obj) == fn:
                    return function_name, obj
            raise KeyError(f"No invokable function named {fn!r}")

        for function_name, obj in invokables.items():
            if obj is fn:
                return function_name, obj

        raise KeyError(f"Callable {fn!r} is not registered with module {self.name!r}")

    def _resolve_job(self, job: str | Callable[..., Any]) -> tuple[str, Callable[..., Any]]:
        jobs = self._collect_jobs()

        if isinstance(job, str):
            direct = jobs.get(job)
            if direct is not None:
                return job, direct
            for job_name, obj in jobs.items():
                if _callable_name(obj) == job:
                    return job_name, obj
            raise KeyError(f"No job named {job!r}")

        for job_name, obj in jobs.items():
            if obj is job:
                return job_name, obj

        raise KeyError(f"Callable {job!r} is not registered as a job on module {self.name!r}")

    # ── Introspection ──────────────────────────────────────────────────────

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "storage": list(self._storage.keys()),
            "functions": list(self._functions.keys()),
            "jobs": list(self._jobs.keys()),
            "channels": list(self._channels.keys()),
            "schedules": list(self._schedules.keys()),
            "components": list(self._components.keys()),
            "secrets": list(self._secrets.keys()),
            "submodules": {k: v.describe() for k, v in self._submodules.items()},
            "exports": list(self._exports),
        }

    def __repr__(self) -> str:
        return (
            f"Module({self.name!r}, "
            f"storage={list(self._storage)}, "
            f"functions={list(self._functions)})"
        )


def _symbol_export_name(symbol: object) -> str:
    if hasattr(symbol, "__name__"):
        return cast(_HasDunderName, symbol).__name__
    return repr(symbol)


def _callable_name(value: Callable[..., Any]) -> str | None:
    if hasattr(value, "__name__"):
        return cast(_HasDunderName, value).__name__
    return None
