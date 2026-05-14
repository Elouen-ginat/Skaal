"""Adapter for `RELATIONAL` resources.

Phase 4 ships a minimal hook that wires a SQLite-backed session via the
existing `SqliteBackend.open_relational_session` machinery; Postgres
and other relational backends require a richer connection-pool lifecycle
that the deploy layer will own. The current cut treats anything other
than ``sqlite`` as not-yet-wired and points at a follow-up phase.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skaal.binding.model import BoundResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: BoundResource, target: Any) -> None:
    """Wire a SQLite-backed relational session to the runtime (best-effort)."""
    if target is None:
        return
    if bound.external:
        return
    if bound.backend != "sqlite":
        from skaal.errors import RuntimeAdapterMissing

        raise RuntimeAdapterMissing(f"relational/{bound.backend}")

    from skaal.backends.sqlite_backend import SqliteBackend

    path: str = bound.options.get("path", "skaal_local.db")
    backend: SqliteBackend = SqliteBackend(path=path, namespace=target.__name__)

    async def _startup() -> None:
        connect = getattr(backend, "connect", None)
        if connect is not None:
            await connect()

    async def _shutdown() -> None:
        close = getattr(backend, "close", None)
        if close is not None:
            await close()

    # The relational helpers in `skaal.relational` read the backend off
    # the runtime state when no per-class wiring exists.
    runtime.state.relational_backends[target.__name__] = backend
    runtime.add_startup_hook(_startup)
    runtime.add_shutdown_hook(_shutdown)
