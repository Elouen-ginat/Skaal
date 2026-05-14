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
  state to the adapter-specific registries kept here.
- The runtime makes no assumptions about the adapter — there is no
  abstract base; adapter modules just expose a `register` callable.

Phase 4 (ADR 032) wires the kinds the local defaults table emits.
Adapters for `RELATIONAL`, `BLOB`, `CHANNEL`, `SCHEDULE`, `JOB` raise
`RuntimeAdapterMissing` rather than silently no-oping so any user
hitting them gets a clear pointer.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from skaal.binding.model import BoundPlan, BoundResource
from skaal.errors import RuntimeResourceUnresolved
from skaal.runtime.dispatch import dispatch_for

if TYPE_CHECKING:
    from starlette.types import ASGIApp

    from skaal.app import App


StartupHook = Callable[[], Awaitable[None]]
ShutdownHook = Callable[[], Awaitable[None]]


@dataclass
class _Route:
    method: str
    path: str
    endpoint: Callable[..., Awaitable[Any]]


@dataclass
class _Mount:
    path: str
    app: ASGIApp


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
    state: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_bound_plan(cls, bound: BoundPlan, app: App) -> LocalRuntime:
        """Build a runtime from a `BoundPlan`, registering every resource."""
        runtime = cls(bound=bound, app=app)
        for resource in bound.resources:
            target = runtime._resolve(resource)
            adapter = dispatch_for(resource.inferred.kind)
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
        from collections.abc import AsyncIterator
        from contextlib import asynccontextmanager

        from starlette.applications import Starlette
        from starlette.routing import Mount, Route

        runtime = self

        @asynccontextmanager
        async def _lifespan(_: Starlette) -> AsyncIterator[None]:
            for hook in runtime.startup_hooks:
                await hook()
            try:
                yield
            finally:
                for hook in reversed(runtime.shutdown_hooks):
                    await hook()

        routes: list[Any] = [
            Route(r.path, r.endpoint, methods=[r.method]) for r in self.routes
        ]
        # Mounts come after routes so explicit per-function routes win
        # when paths collide (e.g. a user mounting "/" alongside an
        # `@app.function` at "/predict").
        routes.extend(Mount(m.path, app=m.app) for m in self.mounts)
        return Starlette(routes=routes, lifespan=_lifespan)

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

        asgi = self.build_asgi()
        uvicorn.run(asgi, host=host, port=port, log_level="info")

    # ── Resource resolution ──────────────────────────────────────────────

    def _resolve(self, resource: BoundResource) -> Any:
        """Look up the live Python object behind a `BoundResource.id`."""
        rid = resource.inferred.id
        bare = rid.split(":")[-1].split(".")[-1]

        for name, obj in self.app._storage.items():
            if name == bare:
                return obj
        for name, obj in self.app._functions.items():
            if name == bare:
                return obj
        for name, obj in self.app._channels.items():
            if name == bare:
                return obj
        for name, obj in self.app._jobs.items():
            if name == bare:
                return obj
        for name, obj in self.app._schedules.items():
            if name == bare:
                return obj

        # ASGI mounts are keyed by path rather than name; the adapter
        # reads them from `app._asgi_path_mounts` directly.
        if resource.inferred.kind.value == "asgi_service":
            return self.app

        # Secrets carry their identity in the resource ID itself; no
        # live Python object backs them on the App side.
        if resource.inferred.kind.value == "secret":
            return None

        raise RuntimeResourceUnresolved(rid)


def serve(
    bound: BoundPlan,
    app: App,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """One-call wrapper around `LocalRuntime.from_bound_plan(...).serve(...)`."""
    LocalRuntime.from_bound_plan(bound, app).serve(host=host, port=port)


__all__ = ["LocalRuntime", "serve"]
