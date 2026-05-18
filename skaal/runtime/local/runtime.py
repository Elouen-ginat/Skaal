"""`LocalRuntime` — the in-process executor for a `BoundPlan`."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.types import ASGIApp

from skaal.binding.model import Plan, PlannedResource
from skaal.errors import RuntimeResourceUnresolved
from skaal.runtime.local.dispatch import dispatch_for

if TYPE_CHECKING:
    from skaal.app import App


StartupHook = Callable[[], Awaitable[None]]
ShutdownHook = Callable[[], Awaitable[None]]
JobPayload = dict[str, Any]
ScheduleEntry = tuple[PlannedResource, Callable[..., Awaitable[Any]]]


@dataclass(frozen=True)
class _Route:
    method: str
    path: str
    endpoint: Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class _Mount:
    path: str
    app: ASGIApp


@dataclass
class RuntimeState:
    """Typed adapter-side registries the runtime carries."""

    relational_backends: dict[str, Any] = field(default_factory=dict)
    job_queues: dict[str, asyncio.Queue[JobPayload]] = field(default_factory=dict)
    schedules: list[ScheduleEntry] = field(default_factory=list)
    scheduler_started: bool = False
    scheduler: Any = None
    invokables: dict[str, Callable[..., Awaitable[Any]]] = field(default_factory=dict)
    invokable_streams: dict[str, Callable[..., AsyncIterator[Any]]] = field(default_factory=dict)


@dataclass
class LocalRuntime:
    """An in-process runtime built from a `BoundPlan`."""

    bound: Plan
    app: App
    routes: list[_Route] = field(default_factory=list)
    mounts: list[_Mount] = field(default_factory=list)
    startup_hooks: list[StartupHook] = field(default_factory=list)
    shutdown_hooks: list[ShutdownHook] = field(default_factory=list)
    state: RuntimeState = field(default_factory=RuntimeState)

    @classmethod
    def from_bound_plan(cls, bound: Plan, app: App) -> LocalRuntime:
        runtime: LocalRuntime = cls(bound=bound, app=app)
        for resource in bound.resources:
            target: Any = runtime._resolve(resource)
            adapter: Callable[[LocalRuntime, PlannedResource, Any], None] = dispatch_for(
                resource.inferred.kind
            )
            adapter(runtime, resource, target)
        return runtime

    def add_route(
        self,
        path: str,
        endpoint: Callable[..., Awaitable[Any]],
        *,
        method: str = "POST",
    ) -> None:
        self.routes.append(_Route(method=method.upper(), path=path, endpoint=endpoint))

    def add_mount(self, path: str, asgi_app: ASGIApp) -> None:
        self.mounts.append(_Mount(path=path, app=asgi_app))

    def add_startup_hook(self, hook: StartupHook) -> None:
        self.startup_hooks.append(hook)

    def add_shutdown_hook(self, hook: ShutdownHook) -> None:
        self.shutdown_hooks.append(hook)

    def build_asgi(self) -> ASGIApp:
        runtime: LocalRuntime = self

        @asynccontextmanager
        async def _lifespan(_: Starlette) -> AsyncIterator[None]:
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
        routes.extend(Mount(m.path, app=m.app) for m in self.mounts)
        return Starlette(routes=routes, lifespan=_lifespan)

    async def invoke(self, function_name: str, kwargs: dict[str, Any]) -> Any:
        fn: Callable[..., Awaitable[Any]] | None = self.state.invokables.get(function_name)
        if fn is None:
            raise KeyError(f"No invokable function named {function_name!r}")
        return await fn(**kwargs)

    def invoke_stream(
        self,
        function_name: str,
        kwargs: dict[str, Any],
    ) -> AsyncIterator[Any]:
        fn: Callable[..., AsyncIterator[Any]] | None = self.state.invokable_streams.get(
            function_name
        )
        if fn is None:
            raise KeyError(f"No invokable stream named {function_name!r}")
        return fn(**kwargs)

    async def shutdown(self) -> None:
        for hook in reversed(self.shutdown_hooks):
            await hook()

    def serve(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        import uvicorn

        asgi: ASGIApp = self.build_asgi()
        uvicorn.run(asgi, host=host, port=port, log_level="info")

    def _resolve(self, resource: PlannedResource) -> Any:
        self.app._autodiscover_declarations()
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

        if resource.inferred.kind.value == "asgi_service":
            return self.app
        if resource.inferred.kind.value == "secret":
            return None

        raise RuntimeResourceUnresolved(resource.inferred.id)


def serve(
    bound: Plan,
    app: App,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    LocalRuntime.from_bound_plan(bound, app).serve(host=host, port=port)


__all__ = ["LocalRuntime", "RuntimeState", "serve"]
