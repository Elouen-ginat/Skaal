"""Adapter that wires a `Store[T]` subclass to a live local backend.

Phase 4 supports the two backends the local defaults table emits for
the `STORE` kind: `sqlite` (persistent) and `redis` (when explicitly
pinned via `Store[T, Redis]`). The adapter constructs the backend,
calls `StoreClass.wire(backend)`, and registers a shutdown hook so the
connection is closed cleanly when the runtime stops.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skaal.binding.model import PlannedResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: PlannedResource, target: Any) -> None:
    """Construct the chosen backend and bind it to ``target`` (the Store class)."""
    if target is None:
        return
    if bound.external:
        # External stores connect via env-config in `Environment.backends`
        # — outside Phase 4's local-runtime scope.
        return

    backend: Any = _build_backend(bound, target)
    target.wire(backend)

    async def _startup() -> None:
        connect = getattr(backend, "connect", None)
        if connect is not None:
            await connect()

    async def _shutdown() -> None:
        close = getattr(backend, "close", None)
        if close is not None:
            await close()

    runtime.add_startup_hook(_startup)
    runtime.add_shutdown_hook(_shutdown)


def _build_backend(bound: PlannedResource, target: Any) -> Any:
    name: str = bound.backend
    namespace: str = target.__name__

    if name == "sqlite":
        from skaal.backends.sqlite_backend import SqliteBackend

        path: str = bound.options.get("path", "skaal_local.db")
        return SqliteBackend(path=path, namespace=namespace)

    if name == "redis":
        try:
            from skaal.backends.redis_backend import RedisBackend
        except Exception as exc:  # pragma: no cover - import error path
            from skaal.errors import MissingExtraError

            raise MissingExtraError(
                "redis adapter requires `redis>=5` — install the `redis` extra."
            ) from exc
        url: str = bound.options.get("url", "redis://localhost:6379/0")
        return RedisBackend(url=url, namespace=namespace)

    from skaal.errors import RuntimeAdapterMissing

    raise RuntimeAdapterMissing(f"store/{name}")
