"""`LocalRuntime` — the in-process executor for a `BoundPlan`.

The runtime is constructed via `LocalRuntime.from_bound_plan(bound, app)`
and started with `serve(host, port)`. Under the hood it builds a single
Starlette `Router`, registers every `BoundResource` through the matching
adapter, then runs uvicorn against the Starlette app.

The contract with adapters is intentionally narrow:

- The runtime hands an adapter `(runtime, bound_resource, live_target)`.
  ``live_target`` is the user's `Store` subclass / `@app.function`
  callable / channel instance / ASGI app discovered via `_resolve`.
- The adapter is free to call `runtime.add_route`, `runtime.add_mount`,
  `runtime.add_startup_hook`, `runtime.add_shutdown_hook`, or attach
  state to the typed registries on `runtime.state`.
- The runtime makes no assumptions about the adapter — there is no
  abstract base; adapter modules just expose a `register` callable.

Phase 4 (ADR 032) wires the kinds the local defaults table emits.
Adapters for `RELATIONAL`, `BLOB`, `CHANNEL`, `SCHEDULE`, `JOB` raise
`RuntimeAdapterMissing` rather than silently no-oping so any user
hitting them gets a clear pointer.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.types import ASGIApp

from skaal.binding.model import BoundPlan, BoundResource
from skaal.errors import RuntimeResourceUnresolved
from skaal.runtime.dispatch import dispatch_for

if TYPE_CHECKING:
    from skaal.app import App


StartupHook = Callable[[], Awaitable[None]]
ShutdownHook = Callable[[], Awaitable[None]]
JobPayload = dict[str, Any]
ScheduleEntry = tuple[BoundResource, Callable[..., Awaitable[Any]]]


@dataclass(frozen=True)
class _Route:
    """Internal record for a registered HTTP route."""

    method: str
    path: str
    endpoint: Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class _Mount:
    """Internal record for an ASGI sub-app mount."""

    path: str
    app: ASGIApp


@dataclass
class RuntimeState:
    """Typed adapter-side registries the runtime carries.

    Each field is owned by exactly one adapter; the runtime never reads
    them directly. They are collected here (rather than per-adapter
    module globals) so unit tests can construct an empty runtime and
    inspect what an adapter registered without import-order surprises.
    """

    relational_backends: dict[str, Any] = field(default_factory=dict)
    job_queues: dict[str, asyncio.Queue[JobPayload]] = field(default_factory=dict)
    schedules: list[ScheduleEntry] = field(default_factory=list)
    scheduler_started: bool = False
    scheduler: Any = None
    invokables: dict[str, Callable[..., Awaitable[Any]]] = field(default_factory=dict)
    invokable_streams: dict[str, Callable[..., AsyncIterator[Any]]] = field(
        default_factory=dict
    )


@dataclass
class LocalRuntime:
    """An in-process runtime built from a `BoundPlan`.

    Construct with `LocalRuntime.from_bound_plan(bound, app)` rather than
    the dataclass constructor; the factory walks the plan and registers
    every adapter before handing back a runtime ready to `serve()`.
    """

    bound: BoundPlan
    app: App
    routes: list[_Route] = field(default_factory=list)
    mounts: list[_Mount] = field(default_factory=list)
    startup_hooks: list[StartupHook] = field(default_factory=list)
    shutdown_hooks: list[ShutdownHook] = field(default_factory=list)
    state: RuntimeState = field(default_factory=RuntimeState)

    @classmethod
    def from_bound_plan(cls, bound: BoundPlan, app: App) -> LocalRuntime:
        """Build a runtime from a `BoundPlan`, registering every resource."""
        runtime: LocalRuntime = cls(bound=bound, app=app)
        for resource in bound.resources:
            target: Any = runtime._resolve(resource)
            adapter: Callable[[LocalRuntime, BoundResource, Any], None] = (
                dispatch_for(resource.inferred.kind)
            )
            adapter(runtime, resource, target)
        return runtime

    # ── Adapter-facing registration helpers ───────────────────────────────

    def add_route(
        self,
        path: str,
        endpoint: Callable[..., Awaitable[Any]],
        *,
        method: str = "POST",
    ) -> None:
        """Register an HTTP route on the Starlette router."""
        self.routes.append(_Route(method=method.upper(), path=path, endpoint=endpoint))

    def add_mount(self, path: str, asgi_app: ASGIApp) -> None:
        """Mount a sub-ASGI app at ``path``."""
        self.mounts.append(_Mount(path=path, app=asgi_app))

    def add_startup_hook(self, hook: StartupHook) -> None:
        """Register a coroutine to await before serving traffic."""
        self.startup_hooks.append(hook)

    def add_shutdown_hook(self, hook: ShutdownHook) -> None:
        """Register a coroutine to await on shutdown (LIFO order)."""
        self.shutdown_hooks.append(hook)

    # ── Public lifecycle ─────────────────────────────────────────────────

    def build_asgi(self) -> ASGIApp:
        """Build the Starlette ASGI app without serving it (used by tests)."""
        runtime: LocalRuntime = self

        @asynccontextmanager
        async def _lifespan(_: Starlette) -> AsyncIterator[None]:
            # The runtime binds itself to the app for the duration of
            # the serve loop so `Module.invoke(...)` / `Module.invoke_stream(...)`
            # can dispatch through `runtime.invoke{,_stream}`. The bind
            # happens before startup hooks so hooks themselves can call
            # `app.invoke(...)` if they need to.
            runtime.app._bind_runtime(runtime)
            try:
                for startup in runtime.startup_hooks:
                    await startup()
                try:
                    yield
                finally:
                    for shutdown in reversed(runtime.shutdown_hooks):
                        await shutdown()
            finally:
                runtime.app._unbind_runtime(runtime)

        routes: list[Route | Mount] = [
            Route(r.path, r.endpoint, methods=[r.method]) for r in self.routes
        ]
        # Mounts come after routes so explicit per-function routes win
        # when paths collide (e.g. a user mounting "/" alongside an
        # `@app.function` at "/predict").
        routes.extend(Mount(m.path, app=m.app) for m in self.mounts)
        return Starlette(routes=routes, lifespan=_lifespan)

    # ── In-process invocation surface ────────────────────────────────────

    async def invoke(self, function_name: str, kwargs: dict[str, Any]) -> Any:
        """Dispatch a registered `@app.function` callable in-process.

        Used by `Module.invoke(...)` so users can call functions through
        the same resilience chain that the HTTP route uses, without
        round-tripping through HTTP. Async-generator-shaped functions
        are not invokable through this entry point — use
        `invoke_stream(...)` instead.
        """
        fn: Callable[..., Awaitable[Any]] | None = self.state.invokables.get(function_name)
        if fn is None:
            raise KeyError(f"No invokable function named {function_name!r}")
        return await fn(**kwargs)

    def invoke_stream(
        self,
        function_name: str,
        kwargs: dict[str, Any],
    ) -> AsyncIterator[Any]:
        """Dispatch a registered async-generator `@app.function` in-process.

        Returns the underlying `AsyncIterator` directly; the caller is
        expected to ``async for`` over it (e.g. inside a Starlette
        `StreamingResponse`). Streams skip the resilience chain — retry
        semantics on a partially-consumed stream are ill-defined and
        deferred to a richer streaming policy in a later phase.
        """
        fn: Callable[..., AsyncIterator[Any]] | None = self.state.invokable_streams.get(
            function_name
        )
        if fn is None:
            raise KeyError(f"No invokable stream named {function_name!r}")
        return fn(**kwargs)

    async def shutdown(self) -> None:
        """Run every registered shutdown hook in LIFO order.

        Exposed for tests and programmatic shutdown — `serve()` calls the
        same hooks through Starlette's lifespan.
        """
        for hook in reversed(self.shutdown_hooks):
            await hook()

    def serve(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        """Build the ASGI app and run it via uvicorn (blocking)."""
        import uvicorn

        asgi: ASGIApp = self.build_asgi()
        uvicorn.run(asgi, host=host, port=port, log_level="info")

    # ── Resource resolution ──────────────────────────────────────────────

    def _resolve(self, resource: BoundResource) -> Any:
        """Look up the live Python object behind a `BoundResource.id`."""
        bare: str = resource.inferred.source.bare_name

        registries: tuple[dict[str, Any], ...] = (
            self.app._storage,
            self.app._functions,
            self.app._channels,
            self.app._jobs,
            self.app._schedules,
        )
        for registry in registries:
            obj: Any = registry.get(bare)
            if obj is not None:
                return obj

        # ASGI mounts are keyed by path rather than name; the adapter
        # reads them from `app._asgi_path_mounts` directly.
        if resource.inferred.kind.value == "asgi_service":
            return self.app

        # Secrets carry their identity in the resource ID itself; no
        # live Python object backs them on the App side.
        if resource.inferred.kind.value == "secret":
            return None

        raise RuntimeResourceUnresolved(resource.inferred.id)


def serve(
    bound: BoundPlan,
    app: App,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """One-call wrapper around `LocalRuntime.from_bound_plan(...).serve(...)`."""
    LocalRuntime.from_bound_plan(bound, app).serve(host=host, port=port)


__all__ = ["LocalRuntime", "RuntimeState", "serve"]
