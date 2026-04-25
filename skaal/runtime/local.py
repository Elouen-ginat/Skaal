"""LocalRuntime — serve a Skaal App in-process for local development."""

from __future__ import annotations

import inspect
import json
import traceback
from pathlib import Path
from typing import Any, cast

from skaal.backends.local_backend import LocalMap
from skaal.runtime._local_scheduler import _LocalSchedulerMixin
from skaal.runtime._local_server import _LocalServerMixin


def _wire_channel(channel_obj: Any) -> None:
    """Replace stub send/receive on a Channel instance with a local backend."""
    from skaal.channel import wire_local

    wire_local(channel_obj)


class LocalRuntime(_LocalServerMixin, _LocalSchedulerMixin):
    """
    Runs a Skaal App locally as a minimal asyncio HTTP server.

    - Each ``@app.function()`` becomes a ``POST /{name}`` endpoint.
    - Storage classes are patched with in-memory :class:`~skaal.backends.local_backend.LocalMap`
      backends (or overrides supplied via *backend_overrides*).
    - Channel instances are wired to :class:`~skaal.runtime.channels.LocalChannel`.
    - ``GET /`` returns a JSON index of available endpoints.
    - ``GET /health`` returns ``{"status": "ok"}``.

    Intended for development and testing only — not production.

    Usage::

        runtime = LocalRuntime(app, host="127.0.0.1", port=8000)
        asyncio.run(runtime.serve())
    """

    def __init__(
        self,
        app: Any,
        host: str = "127.0.0.1",
        port: int = 8000,
        backend_overrides: dict[str, Any] | None = None,
    ) -> None:
        self.app = app
        self.host = host
        self.port = port
        self._backends: dict[str, Any] = {}
        self._backend_overrides = backend_overrides or {}
        self._patch_storage()
        self._patch_channels()
        # Cache the function map so it's not rebuilt on every HTTP request
        self._function_cache = self._collect_functions()
        # Pre-build resilience wrappers so breaker/bulkhead state is per-function
        # and persists across invocations.
        from skaal.runtime.middleware import wrap_handler

        self._invokers: dict[str, Any] = {
            name: wrap_handler(fn, fallback_lookup=self._function_cache.get)
            for name, fn in self._function_cache.items()
        }
        # Pattern engines are started lazily by ``serve()`` so an asyncio loop
        # is already running when they spin up background tasks.
        self._engines: list[Any] = []
        self.sagas: dict[str, Any] = {}
        # Storage-class references indexed by name so engines can look them up.
        self._stores: dict[str, Any] = {
            qname: obj
            for qname, obj in self.app._collect_all().items()
            if isinstance(obj, type) and hasattr(obj, "__skaal_storage__")
        }

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _patch_storage(self) -> None:
        """Wire all registered storage classes with appropriate backends."""
        from skaal.backends.chroma_backend import ChromaVectorBackend
        from skaal.backends.sqlite_backend import SqliteBackend
        from skaal.relational import is_relational_model, wire_relational_model
        from skaal.storage import Store
        from skaal.vector import VectorStore, is_vector_model

        for qname, obj in self.app._collect_all().items():
            if not (isinstance(obj, type) and hasattr(obj, "__skaal_storage__")):
                continue

            backend = self._backend_overrides.get(qname) or self._backend_overrides.get(
                obj.__name__
            )

            if is_relational_model(obj):
                backend = backend or SqliteBackend(Path("skaal_local.db"), namespace=qname)
                self._backends[qname] = backend
                wire_relational_model(obj, backend)
                continue

            if is_vector_model(obj):
                backend = backend or ChromaVectorBackend(Path("skaal_chroma"), namespace=qname)
                self._backends[qname] = backend
                cast(type[VectorStore[Any]], obj).wire(backend)
                continue

            if issubclass(obj, Store):
                backend = backend or LocalMap()
                self._backends[qname] = backend
                obj.wire(backend)
            elif issubclass(obj, VectorStore):
                backend = backend or ChromaVectorBackend(Path("skaal_chroma"), namespace=qname)
                self._backends[qname] = backend
                obj.wire(backend)

    def _patch_channels(self) -> None:
        """Wire Channel instances registered with the app to LocalChannel."""
        from skaal.channel import Channel as SkaalChannel

        for obj in self.app._collect_all().values():
            if isinstance(obj, SkaalChannel):
                _wire_channel(obj)

    # ── Factory methods ────────────────────────────────────────────────────────

    @staticmethod
    def _build_backends(app: Any, backend_factory: Any) -> dict[str, Any]:
        """
        Build a backends dict for all storage classes in app using a factory function.

        Args:
            app: The Skaal App.
            backend_factory: Callable that takes (qname, obj) and returns a backend instance.

        Returns:
            Dict mapping fully-qualified names to backend instances.
        """
        return {
            qname: backend_factory(qname, obj)
            for qname, obj in app._collect_all().items()
            if isinstance(obj, type) and hasattr(obj, "__skaal_storage__")
        }

    @classmethod
    def from_redis(
        cls,
        app: Any,
        redis_url: str,
        host: str = "127.0.0.1",
        port: int = 8000,
    ) -> "LocalRuntime":
        """Create a ``LocalRuntime`` using Redis backends for all storage classes."""
        from skaal.backends.redis_backend import RedisBackend
        from skaal.relational import is_relational_model
        from skaal.vector import is_vector_model

        def _make_backend(qname: str, obj: Any) -> RedisBackend:
            if is_relational_model(obj) or is_vector_model(obj):
                raise ValueError(
                    "LocalRuntime.from_redis() does not support @app.relational or @app.vector models."
                )
            return RedisBackend(url=redis_url, namespace=qname.replace(".", "_").lower())

        backends = cls._build_backends(app, _make_backend)
        return cls(app, host=host, port=port, backend_overrides=backends)

    @classmethod
    def from_sqlite(
        cls,
        app: Any,
        db_path: str | Path = "skaal_local.db",
        host: str = "127.0.0.1",
        port: int = 8000,
    ) -> "LocalRuntime":
        """Create a ``LocalRuntime`` backed by SQLite."""
        from skaal.backends.chroma_backend import ChromaVectorBackend
        from skaal.backends.sqlite_backend import SqliteBackend
        from skaal.vector import is_vector_model

        def _make_backend(qname: str, obj: Any) -> Any:
            if is_vector_model(obj):
                chroma_path = Path(db_path).parent / f"{Path(db_path).stem}_chroma"
                return ChromaVectorBackend(chroma_path, namespace=qname)
            return SqliteBackend(Path(db_path), namespace=qname)

        backends = cls._build_backends(app, _make_backend)
        return cls(app, host=host, port=port, backend_overrides=backends)

    @classmethod
    def from_postgres(
        cls,
        app: Any,
        dsn: str,
        host: str = "127.0.0.1",
        port: int = 8000,
        min_size: int = 1,
        max_size: int = 5,
    ) -> "LocalRuntime":
        """
        Create a ``LocalRuntime`` backed by PostgreSQL.

        Args:
            app:      The Skaal :class:`~skaal.app.App`.
            dsn:      asyncpg connection string, e.g.
                      ``"postgresql://user:pass@localhost/mydb"``.
            min_size: Connection pool minimum size.
            max_size: Connection pool maximum size.
        """
        from skaal.backends.pgvector_backend import PgVectorBackend
        from skaal.backends.postgres_backend import PostgresBackend
        from skaal.vector import is_vector_model

        def _make_backend(qname: str, obj: Any) -> Any:
            if is_vector_model(obj):
                return PgVectorBackend(dsn=dsn, namespace=qname)
            return PostgresBackend(dsn=dsn, namespace=qname, min_size=min_size, max_size=max_size)

        backends = cls._build_backends(app, _make_backend)
        return cls(app, host=host, port=port, backend_overrides=backends)

    # ── HTTP dispatch ──────────────────────────────────────────────────────────

    def _collect_functions(self) -> dict[str, Any]:
        """Flat map of qualified_name → callable for all HTTP-invocable functions.

        Includes:
        - ``@app.function()`` decorated callables (have ``__skaal_compute__``)
        - ``@app.schedule()`` decorated callables (invocable by Cloud Scheduler /
          EventBridge; excluded from the public ``GET /`` index)
        """
        funcs: dict[str, Any] = {
            qname: obj
            for qname, obj in self.app._collect_all().items()
            if callable(obj) and hasattr(obj, "__skaal_compute__")
        }
        # Also expose top-level functions by short name for convenience.
        for name, fn in self.app._functions.items():
            funcs.setdefault(name, fn)
        # Include scheduled functions so Cloud Scheduler / EventBridge can invoke
        # them via HTTP POST.  They are excluded from the GET / listing.
        for name, fn in getattr(self.app, "_schedules", {}).items():
            funcs.setdefault(name, fn)
        return funcs

    def _collect_schedules(self) -> dict[str, Any]:
        """Flat map of name → callable for all ``@app.schedule()`` functions."""
        return dict(getattr(self.app, "_schedules", {}))

    async def _dispatch(self, method: str, path: str, body: bytes) -> tuple[Any, int]:
        """Route an HTTP request to a registered function."""
        funcs = self._function_cache

        if method == "GET" and path in ("/", ""):
            # Only expose @app.function() endpoints in the public index.
            public = [n for n in sorted(funcs) if not hasattr(funcs[n], "__skaal_schedule__")]
            return {
                "app": self.app.name,
                "endpoints": [{"path": f"/{n}", "function": n} for n in public],
                "storage": list(self._backends.keys()),
            }, 200

        if method == "GET" and path == "/health":
            return {"status": "ok", "app": self.app.name}, 200

        if method == "POST":
            fn_name = path.lstrip("/")
            if fn_name not in funcs:
                return {"error": f"No function {fn_name!r}. Available: {sorted(funcs)}"}, 404

            fn = funcs[fn_name]
            kwargs: dict[str, Any] = {}
            if body:
                try:
                    kwargs = json.loads(body)
                    if not isinstance(kwargs, dict):
                        return {"error": "Request body must be a JSON object"}, 400
                except json.JSONDecodeError as exc:
                    return {"error": f"Invalid JSON: {exc}"}, 400

            # Strip the internal schedule-trigger marker and inject ScheduleContext
            # when Cloud Scheduler / EventBridge includes it in the request body.
            is_schedule_invocation = kwargs.pop("_skaal_trigger", None) is not None
            if is_schedule_invocation:
                sig = inspect.signature(fn)
                if "ctx" in sig.parameters:
                    from datetime import timezone

                    from skaal.schedule import ScheduleContext

                    kwargs["ctx"] = ScheduleContext(
                        fired_at=__import__("datetime").datetime.now(timezone.utc)
                    )

            invoker = self._invokers.get(fn_name)
            try:
                if invoker is not None:
                    result = await invoker(**kwargs)
                else:
                    result = await fn(**kwargs) if inspect.iscoroutinefunction(fn) else fn(**kwargs)
                return result, 200
            except TypeError as exc:
                return {"error": f"Bad arguments for {fn_name!r}: {exc}"}, 422
            except Exception as exc:  # noqa: BLE001
                return {"error": str(exc), "traceback": traceback.format_exc()}, 500

        return {"error": f"Method {method} not allowed"}, 405

    @property
    def functions(self) -> dict[str, Any]:
        """Expose the handler registry to pattern engines (read-only view)."""
        return self._function_cache

    @property
    def stores(self) -> dict[str, Any]:
        """Expose storage classes by name to pattern engines."""
        return self._stores

    async def shutdown(self) -> None:
        """
        Shut down the runtime by closing all backend connections.

        Called automatically when serve() exits. Can also be called explicitly
        to clean up resources.
        """
        import contextlib

        for engine in self._engines:
            with contextlib.suppress(Exception):
                await engine.stop()
        self._engines = []

        for backend in self._backends.values():
            with contextlib.suppress(Exception):
                await backend.close()
