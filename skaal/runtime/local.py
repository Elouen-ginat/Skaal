"""LocalRuntime — serve a Skaal App in-process for local development."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import traceback
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from rq import Queue
from rq.serializers import JSONSerializer

from skaal.backends.local_backend import LocalMap
from skaal.runtime.base import _SKAAL_INVOKE_PREFIX, BaseRuntime
from skaal.runtime.jobs import (
    JobWorkerTelemetry,
    build_rq_retry,
    build_worker,
    close_job_connection,
    default_job_connection,
    ensure_json_payload,
    failed_registry,
    job_handle_from_rq_job,
    job_queue_name,
    normalize_scheduled_for,
    promote_scheduled_jobs,
    register_runtime,
    scheduled_registry,
    unique_job_id,
    unregister_runtime,
    utc_now,
)
from skaal.types import Duration, JobHandle, JobSpec

if TYPE_CHECKING:
    import httpx

    from skaal.runtime.telemetry import RuntimeTelemetry
    from skaal.types import TelemetryConfig

_MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MiB — reject oversized request bodies
log = logging.getLogger("skaal.runtime")
_SKAAL_AGENT_PREFIX = "/_skaal/agents/"


def _format_banner(title: str, lines: list[str]) -> str:
    return "\n".join(["", title, *lines, ""])


def _wire_channel(channel_obj: Any) -> None:
    """Replace stub send/receive on a Channel instance with a local backend."""
    from skaal.channel import wire_local

    wire_local(channel_obj)


class LocalRuntime(BaseRuntime):
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
        *,
        telemetry: "TelemetryConfig | None" = None,
        telemetry_runtime: "RuntimeTelemetry | None" = None,
        auth_http_client: "httpx.AsyncClient | None" = None,
        kv_backend_factory: Callable[[str], Any] | None = None,
        job_connection: Any | None = None,
    ) -> None:
        self._kv_backend_factory = kv_backend_factory or (lambda _namespace: LocalMap())
        self._job_connection_override = job_connection
        self.sagas: dict[str, Any] = {}
        super().__init__(
            app,
            host=host,
            port=port,
            backend_overrides=backend_overrides,
            telemetry=telemetry,
            telemetry_runtime=telemetry_runtime,
            auth_http_client=auth_http_client,
        )
        self._schedule_autostart()

    def _initialize_runtime_state(self) -> None:
        self._agent_backends: dict[str, Any] = {}
        self._agent_routes = self._collect_agents()
        self._agent_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._job_handlers = self._collect_jobs()
        self._job_connection: Any | None = None
        self._job_queue: Queue | None = None
        self._job_loop: asyncio.AbstractEventLoop | None = None
        self._job_runtime_token = f"skaal-runtime:{self.app.name}"
        self._job_stop = asyncio.Event()
        self._job_task: asyncio.Task[None] | None = None
        self._job_telemetry = JobWorkerTelemetry()
        self._autostart_task: asyncio.Task[None] | None = None
        self._background_jobs_thread_started = False
        self._job_worker_start_suppressed = False

    def _schedule_autostart(self) -> None:
        if self._started or self._autostart_task is not None:
            return
        if not self._has_pending_job_work():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._autostart_task = loop.create_task(
            self.ensure_started(),
            name=f"skaal-runtime-start:{self.app.name}",
        )
        self._autostart_task.add_done_callback(self._finalize_autostart)

    def _finalize_autostart(self, task: asyncio.Task[None]) -> None:
        self._autostart_task = None
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.warning("[skaal/runtime] background startup failed: %s", exc)

    def _has_pending_job_work(self) -> bool:
        if not self._job_handlers:
            return False
        queue = self._job_queue_instance()
        return len(queue) > 0 or len(scheduled_registry(queue)) > 0

    def _default_kv_backend(self, namespace: str) -> Any:
        return self._kv_backend_factory(namespace)

    def _default_relational_backend(self, namespace: str) -> Any:
        from skaal.backends.sqlite_backend import SqliteBackend

        return SqliteBackend(Path("skaal_local.db"), namespace=namespace)

    def _default_vector_backend(self, namespace: str) -> Any:
        from skaal.backends.chroma_backend import ChromaVectorBackend

        return ChromaVectorBackend(Path("skaal_chroma"), namespace=namespace)

    def _default_blob_backend(self, namespace: str) -> Any:
        from skaal.backends.file_blob_backend import FileBlobBackend

        return FileBlobBackend(Path(".skaal") / "blobs", namespace=namespace)

    def _wire_channel_instance(self, channel_obj: Any) -> None:
        _wire_channel(channel_obj)

    def _root_payload(self) -> dict[str, Any]:
        public = sorted({*self._public_functions(), *self.app._functions})
        return {
            "app": self.app.name,
            "endpoints": [
                {"path": f"{_SKAAL_INVOKE_PREFIX}{name}", "function": name} for name in public
            ],
            "jobs": sorted(
                name
                for name, (qualified_name, _) in self._job_handlers.items()
                if name == qualified_name
            ),
            "agents": [
                {
                    "path": f"{_SKAAL_AGENT_PREFIX}{name}/{{identity}}/{{handler}}",
                    "agent": name,
                    "handlers": sorted(self._agent_handlers(agent_cls)),
                }
                for name, (qualified_name, agent_cls) in sorted(self._agent_routes.items())
                if name == qualified_name
            ],
            "storage": list(self.stores.keys()),
        }

    def _augment_readiness_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._job_handlers:
            return payload
        payload["jobs"] = {
            "registered_jobs": sorted(
                name
                for name, (qualified_name, _) in self._job_handlers.items()
                if name == qualified_name
            ),
            "worker_running": self._job_task is not None and not self._job_task.done(),
            "queue_depth": self._job_queue_depth(),
            "failed_jobs": self._job_failed_count(),
        }
        return payload

    async def _dispatch_extra_post(
        self,
        path: str,
        request_payload: Any,
        request_headers: Mapping[str, str],
    ) -> tuple[Any, int, Exception | None] | None:
        from skaal.runtime.auth import RuntimeAuthFailure

        agent_target = self._agent_invocation_target(path)
        if agent_target is None:
            return None
        if not isinstance(request_payload, dict):
            return {"error": "Agent request body must be a JSON object"}, 400, None

        args = request_payload.get("args", [])
        kwargs = request_payload.get("kwargs", {})
        if not isinstance(args, list) or not isinstance(kwargs, dict):
            return (
                {"error": "Agent request body must be {'args': [...], 'kwargs': {...}}"},
                400,
                None,
            )

        try:
            auth_claims, auth_subject = await self._authenticate_request(request_headers)
        except RuntimeAuthFailure as exc:
            return {"error": exc.message}, exc.status_code, None

        try:
            agent_name, identity, handler_name = agent_target
            del auth_claims, auth_subject
            result = await self.invoke_agent(agent_name, identity, handler_name, *args, **kwargs)
            return result, 200, None
        except KeyError as exc:
            return {"error": str(exc)}, 404, None
        except TypeError as exc:
            return {"error": f"Bad arguments for agent route {path!r}: {exc}"}, 422, None
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "traceback": traceback.format_exc()}, 500, exc

    async def _close_extra_resources(self) -> None:
        if self._autostart_task is not None and not self._autostart_task.done():
            self._autostart_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._autostart_task
        self._autostart_task = None

        self._job_stop.set()
        if self._job_task is not None:
            self._job_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._job_task
            self._job_task = None
        unregister_runtime(self._job_runtime_token)

        if self._job_connection is not None:
            with suppress(Exception):
                await close_job_connection(self._job_connection)
            self._job_connection = None
        self._job_queue = None

        for backend in self._agent_backends.values():
            with suppress(Exception):
                await backend.close()
        self._agent_backends.clear()

    async def _start_engines(self) -> None:
        await super()._start_engines()
        await self._start_job_worker()

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
        backends: dict[str, Any] = {}
        for qname, obj in app._collect_all().items():
            if not (isinstance(obj, type) and hasattr(obj, "__skaal_storage__")):
                continue
            backend = backend_factory(qname, obj)
            if backend is not None:
                backends[qname] = backend
        return backends

    @staticmethod
    def _normalized_backend_namespace(namespace: str) -> str:
        return namespace.replace(".", "_").lower()

    @staticmethod
    def _plugin_backend(name: str) -> type[Any]:
        from skaal import plugins

        return cast(type[Any], plugins.get_backend(name))

    @classmethod
    def _make_backend_instance(cls, name: str, namespace: str, **config: Any) -> Any:
        backend_cls = cls._plugin_backend(name)

        if name == "sqlite":
            db_path = Path(cast(str | Path, config["db_path"]))
            return backend_cls(db_path, namespace=namespace)
        if name == "redis":
            return backend_cls(
                url=cast(str, config["redis_url"]),
                namespace=cls._normalized_backend_namespace(namespace),
            )
        if name == "firestore":
            return backend_cls(
                collection=cls._normalized_backend_namespace(namespace),
                project=config.get("project"),
                database=cast(str, config.get("database", "(default)")),
            )
        if name == "postgres":
            return backend_cls(
                dsn=cast(str, config["dsn"]),
                namespace=namespace,
                min_size=cast(int, config.get("min_size", 1)),
                max_size=cast(int, config.get("max_size", 5)),
            )
        if name == "dynamodb":
            table_name = cast(str, config["table_name"])
            return backend_cls(
                table_name=f"{table_name}_{cls._normalized_backend_namespace(namespace)}",
                region=cast(str, config.get("region", "us-east-1")),
            )
        raise ValueError(f"LocalRuntime.from_backend() does not know how to configure {name!r}.")

    @classmethod
    def _make_vector_backend_instance(cls, name: str, namespace: str, **config: Any) -> Any:
        if name == "sqlite":
            chroma_cls = cls._plugin_backend("chroma")
            db_path = Path(cast(str | Path, config["db_path"]))
            chroma_path = db_path.parent / f"{db_path.stem}_chroma"
            return chroma_cls(chroma_path, namespace=namespace)
        if name == "postgres":
            pgvector_cls = cls._plugin_backend("pgvector")
            return pgvector_cls(dsn=cast(str, config["dsn"]), namespace=namespace)
        raise ValueError(
            f'LocalRuntime.from_backend({name!r}) does not support @app.storage(kind="vector") models.'
        )

    @classmethod
    def from_backend(
        cls,
        app: Any,
        name: str,
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        **config: Any,
    ) -> "LocalRuntime":
        """Create a ``LocalRuntime`` from a named backend plugin plus backend config."""
        from skaal.blob import is_blob_model
        from skaal.relational import is_relational_model
        from skaal.vector import is_vector_model

        def _make_backend(qname: str, obj: Any) -> Any | None:
            if is_blob_model(obj):
                return None
            if is_vector_model(obj):
                return cls._make_vector_backend_instance(name, qname, **config)
            if is_relational_model(obj) and name not in {"sqlite", "postgres"}:
                raise ValueError(
                    f'LocalRuntime.from_backend({name!r}) does not support @app.storage(kind="relational") models.'
                )
            return cls._make_backend_instance(name, qname, **config)

        backends = cls._build_backends(app, _make_backend)
        return cls(
            app,
            host=host,
            port=port,
            backend_overrides=backends,
            kv_backend_factory=lambda namespace: cls._make_backend_instance(
                name, namespace, **config
            ),
        )

    @classmethod
    def from_redis(
        cls,
        app: Any,
        redis_url: str,
        host: str = "127.0.0.1",
        port: int = 8000,
    ) -> "LocalRuntime":
        """Create a ``LocalRuntime`` using Redis backends for all storage classes."""
        return cls.from_backend(
            app,
            "redis",
            host=host,
            port=port,
            redis_url=redis_url,
        )

    @classmethod
    def from_sqlite(
        cls,
        app: Any,
        db_path: str | Path = "skaal_local.db",
        host: str = "127.0.0.1",
        port: int = 8000,
    ) -> "LocalRuntime":
        """Create a ``LocalRuntime`` backed by SQLite."""
        return cls.from_backend(
            app,
            "sqlite",
            host=host,
            port=port,
            db_path=db_path,
        )

    @classmethod
    def from_firestore(
        cls,
        app: Any,
        project: str | None = None,
        database: str = "(default)",
        host: str = "127.0.0.1",
        port: int = 8000,
    ) -> "LocalRuntime":
        """
        Create a ``LocalRuntime`` using Cloud Firestore backends for all storage classes.

        Each storage class gets its own Firestore collection named after the
        fully-qualified class name (dots replaced with underscores).

        Args:
            app:      The Skaal :class:`~skaal.app.App`.
            project:  GCP project ID.  Defaults to the ambient project from
                      Application Default Credentials.
            database: Firestore database name.  Defaults to ``"(default)"``.
        """
        return cls.from_backend(
            app,
            "firestore",
            host=host,
            port=port,
            project=project,
            database=database,
        )

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
        return cls.from_backend(
            app,
            "postgres",
            host=host,
            port=port,
            dsn=dsn,
            min_size=min_size,
            max_size=max_size,
        )

    @classmethod
    def from_dynamodb(
        cls,
        app: Any,
        table_name: str,
        region: str = "us-east-1",
        host: str = "127.0.0.1",
        port: int = 8000,
    ) -> "LocalRuntime":
        """Create a ``LocalRuntime`` backed by DynamoDB."""
        return cls.from_backend(
            app,
            "dynamodb",
            host=host,
            port=port,
            table_name=table_name,
            region=region,
        )

    def wire_channels_redis(
        self,
        redis_url: str = "redis://localhost:6379",
        namespace: str | None = None,
    ) -> None:
        """Re-wire all Channel instances to use Redis Streams instead of local queues.

        Call after construction to upgrade channels to distributed pub/sub::

            runtime = LocalRuntime(app)
            runtime.wire_channels_redis("redis://localhost:6379")
        """
        from skaal.channel import Channel as SkaalChannel
        from skaal.channel import wire_redis

        ns = namespace or self.app.name
        for name, obj in self.app._collect_all().items():
            if isinstance(obj, SkaalChannel):
                wire_redis(obj, url=redis_url, namespace=ns, topic=name)

    # ── HTTP dispatch ──────────────────────────────────────────────────────────

    def _collect_schedules(self) -> dict[str, Any]:
        """Flat map of name → callable for all ``@app.schedule()`` functions."""
        return dict(getattr(self.app, "_schedules", {}))

    def _collect_jobs(self) -> dict[str, tuple[str, Any]]:
        jobs: dict[str, tuple[str, Any]] = {}
        short_names: dict[str, list[str]] = {}
        for qname, obj in self.app._collect_jobs().items():
            jobs[qname] = (qname, obj)
            short_names.setdefault(getattr(obj, "__name__", qname), []).append(qname)

        for short_name, qualified_names in short_names.items():
            if len(qualified_names) == 1:
                qualified_name = qualified_names[0]
                jobs[short_name] = jobs[qualified_name]

        return jobs

    def _collect_agents(self) -> dict[str, tuple[str, type[Any]]]:
        agents: dict[str, tuple[str, type[Any]]] = {}
        short_names: dict[str, list[str]] = {}
        for qname, obj in self.app._collect_all().items():
            if not (isinstance(obj, type) and hasattr(obj, "__skaal_agent__")):
                continue
            agents[qname] = (qname, obj)
            short_names.setdefault(obj.__name__, []).append(qname)

        for short_name, qualified_names in short_names.items():
            if len(qualified_names) == 1:
                qualified_name = qualified_names[0]
                agents[short_name] = agents[qualified_name]

        return agents

    @staticmethod
    def _agent_invocation_target(path: str) -> tuple[str, str, str] | None:
        if not path.startswith(_SKAAL_AGENT_PREFIX):
            return None
        parts = path[len(_SKAAL_AGENT_PREFIX) :].split("/")
        if len(parts) != 3 or not all(parts):
            return None
        return parts[0], parts[1], parts[2]

    @staticmethod
    def _agent_handlers(agent_cls: type[Any]) -> dict[str, Any]:
        return {
            name: member
            for name, member in inspect.getmembers(agent_cls)
            if callable(member) and getattr(member, "__skaal_handler__", False)
        }

    def _agent_lock(self, agent_name: str, identity: str) -> asyncio.Lock:
        key = (agent_name, identity)
        lock = self._agent_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._agent_locks[key] = lock
        return lock

    def _agent_backend_name(self, agent_name: str) -> str:
        return f"{self.app.name}.__skaal_agents__.{agent_name}"

    def _agent_backend(self, agent_name: str) -> Any:
        backend_name = self._agent_backend_name(agent_name)
        backend = self._agent_backends.get(backend_name)
        if backend is not None:
            return backend

        backend = self._backend_overrides.get(backend_name)
        if backend is None:
            backend = self._kv_backend_factory(backend_name)
        self._agent_backends[backend_name] = backend
        return backend

    @staticmethod
    def _decode_agent_state(raw_state: Any) -> dict[str, Any] | None:
        if raw_state is None:
            return None
        if isinstance(raw_state, str):
            raw_state = json.loads(raw_state)
        if not isinstance(raw_state, dict):
            raise TypeError("Persisted agent state must be a JSON object")
        return raw_state

    def _job_queue_connection(self) -> Any:
        if self._job_connection is None:
            self._job_connection = self._job_connection_override or default_job_connection(
                self.app.name
            )
        return self._job_connection

    def _job_queue_instance(self) -> Queue:
        if self._job_queue is None:
            self._job_queue = Queue(
                job_queue_name(self.app.name),
                connection=self._job_queue_connection(),
                serializer=JSONSerializer,
            )
        return self._job_queue

    def _job_worker_instance(self) -> Any:
        return build_worker(self._job_queue_instance(), self._job_queue_connection())

    def _job_queue_depth(self) -> int:
        if self._job_queue is None:
            return 0
        return len(self._job_queue) + len(scheduled_registry(self._job_queue))

    def _job_failed_count(self) -> int:
        if self._job_queue is None:
            return 0
        return len(failed_registry(self._job_queue))

    async def _start_job_worker(self) -> None:
        if self._job_worker_start_suppressed:
            return
        if not self._job_handlers or self._job_task is not None:
            return
        self._job_loop = asyncio.get_running_loop()
        self._job_queue_instance()
        self._job_worker_instance()
        register_runtime(self._job_runtime_token, self)
        self._job_stop = asyncio.Event()
        self._job_task = asyncio.create_task(
            self._job_worker_loop(),
            name=f"skaal-jobs:{self.app.name}",
        )

    async def enqueue_job(
        self,
        job_name: str,
        *args: Any,
        delay: Duration | str | None = None,
        run_at: Any | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> JobHandle:
        await self.ensure_started()

        resolved = self._job_handlers.get(job_name)
        if resolved is None:
            raise KeyError(f"No job {job_name!r}. Available: {sorted(self._job_handlers)}")

        qualified_name, fn = resolved
        spec = cast(JobSpec, getattr(fn, "__skaal_job__"))
        scheduled_for = normalize_scheduled_for(delay=delay, run_at=run_at)
        normalized_args, normalized_kwargs = ensure_json_payload(args=args, kwargs=kwargs)
        queue = self._job_queue_instance()
        retry = build_rq_retry(spec.retry)
        job_id = unique_job_id(qualified_name, idempotency_key) if idempotency_key else None
        if job_id is not None:
            existing = queue.fetch_job(job_id)
            if existing is not None:
                return job_handle_from_rq_job(existing, fallback_scheduled_for=scheduled_for)
        enqueue_kwargs: dict[str, Any] = {
            "description": qualified_name,
            "retry": retry,
            "result_ttl": 3600,
            "failure_ttl": 86400,
        }
        if job_id is not None:
            enqueue_kwargs["job_id"] = job_id

        if scheduled_for <= utc_now():
            job = queue.enqueue(
                "skaal.runtime.jobs.execute_registered_job",
                self._job_runtime_token,
                qualified_name,
                normalized_args,
                normalized_kwargs,
                **enqueue_kwargs,
            )
        else:
            job = queue.enqueue_at(
                scheduled_for,
                "skaal.runtime.jobs.execute_registered_job",
                self._job_runtime_token,
                qualified_name,
                normalized_args,
                normalized_kwargs,
                **enqueue_kwargs,
            )

        job.meta.setdefault("scheduled_for", scheduled_for.isoformat())
        job.meta.setdefault("skaal_job_name", qualified_name)
        job.save_meta()
        if scheduled_for <= utc_now():
            self._kick_remote_job_worker()
        return job_handle_from_rq_job(job, fallback_scheduled_for=scheduled_for)

    def _kick_remote_job_worker(self) -> None:
        worker_function = os.getenv("SKAAL_JOBS_WORKER_FUNCTION")
        if not worker_function:
            return
        try:
            import boto3
        except ImportError:
            log.warning("[skaal/jobs] boto3 is not available; cannot invoke AWS jobs worker")
            return
        try:
            boto3.client("lambda").invoke(
                FunctionName=worker_function,
                InvocationType="Event",
                Payload=b'{"source":"skaal-jobs-enqueue"}',
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("[skaal/jobs] failed to invoke remote jobs worker: %s", exc)

    async def run_job_worker_burst(self, *, max_jobs: int = 10) -> int:
        if not self._job_handlers:
            return 0

        if not self._started:
            self._job_worker_start_suppressed = True
            try:
                await self.ensure_started()
            finally:
                self._job_worker_start_suppressed = False

        self._job_loop = asyncio.get_running_loop()
        queue = self._job_queue_instance()
        connection = self._job_queue_connection()
        transient_registration = self._job_task is None
        if transient_registration:
            register_runtime(self._job_runtime_token, self)
        try:
            promote_scheduled_jobs(queue, connection)
            queue_depth = self._job_queue_depth()
            self._job_telemetry.queued = queue_depth
            self._job_telemetry.failed = self._job_failed_count()
            self._job_telemetry.last_tick_at = utc_now()
            ready_jobs = len(queue)
            if ready_jobs <= 0:
                return 0

            self._job_telemetry.running = 1
            await asyncio.to_thread(
                self._job_worker_instance().work,
                burst=True,
                max_jobs=max_jobs,
            )
            remaining_jobs = len(queue)
            return max(0, ready_jobs - remaining_jobs)
        finally:
            self._job_telemetry.running = 0
            if transient_registration:
                unregister_runtime(self._job_runtime_token)

    async def _job_worker_loop(self) -> None:
        while not self._job_stop.is_set():
            try:
                queue = self._job_queue_instance()
                promote_scheduled_jobs(queue, self._job_queue_connection())
                queue_depth = self._job_queue_depth()
                self._job_telemetry.queued = queue_depth
                self._job_telemetry.failed = self._job_failed_count()
                self._job_telemetry.last_tick_at = utc_now()
                if len(queue) > 0:
                    self._job_telemetry.running = 1
                    await asyncio.to_thread(
                        self._job_worker_instance().work,
                        burst=True,
                        max_jobs=1,
                    )
                    self._job_telemetry.running = 0
            except Exception as exc:  # noqa: BLE001
                log.warning("[skaal/jobs] worker tick failed: %s", exc)
                self._job_telemetry.running = 0
            try:
                await asyncio.wait_for(self._job_stop.wait(), timeout=0.05)
            except asyncio.TimeoutError:
                continue

    async def _invoke_registered_job(self, job_name: str, *args: Any, **kwargs: Any) -> Any:
        resolved = self._job_handlers.get(job_name)
        if resolved is None:
            raise KeyError(f"No job {job_name!r}. Available: {sorted(self._job_handlers)}")
        _, fn = resolved
        result = fn(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    async def invoke_agent(
        self,
        agent_name: str,
        identity: Any,
        handler_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        resolved = self._agent_routes.get(agent_name)
        if resolved is None:
            raise KeyError(f"No agent {agent_name!r}. Available: {sorted(self._agent_routes)}")

        qualified_name, agent_cls = resolved
        handler = self._agent_handlers(agent_cls).get(handler_name)
        if handler is None:
            raise KeyError(
                f"No handler {handler_name!r} on agent {agent_name!r}. "
                f"Available: {sorted(self._agent_handlers(agent_cls))}"
            )

        identity_key = str(identity)
        persistent = bool(getattr(agent_cls, "__skaal_agent__", {}).get("persistent", True))
        backend = self._agent_backend(qualified_name) if persistent else None

        async with self._agent_lock(qualified_name, identity_key):
            agent = agent_cls()
            setattr(agent, "identity", identity_key)
            persisted_state = self._decode_agent_state(
                await backend.get(identity_key) if backend is not None else None
            )
            agent._load_state(persisted_state)
            bound_handler = getattr(agent, handler_name)
            try:
                result = bound_handler(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
            except Exception:
                if backend is not None:
                    await backend.set(identity_key, persisted_state or {})
                raise

            if backend is not None:
                await backend.set(identity_key, agent._serialize_state())
            return result

    async def _handle_connection(self, reader: Any, writer: Any) -> None:
        """Handle a single raw TCP connection with HTTP/1.0-style request parsing.

        Enforces ``_MAX_BODY_SIZE`` and writes a plain-text HTTP response.
        Intended for testing and low-level inspection; production traffic goes
        through the uvicorn path in :meth:`_serve_skaal`.
        """
        try:
            # Read the request line
            request_line_bytes = await reader.readline()
            if not request_line_bytes:
                return
            request_line = request_line_bytes.decode("utf-8", errors="replace").strip()
            parts = request_line.split(" ", 2)
            if len(parts) < 2:
                return
            method, path = parts[0], parts[1]

            # Read headers until blank line
            headers: dict[str, str] = {}
            while True:
                line_bytes = await reader.readline()
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    break
                if ":" in line:
                    name, _, value = line.partition(":")
                    headers[name.strip().lower()] = value.strip()

            # Enforce body size limit
            content_length = int(headers.get("content-length", "0"))
            if content_length > _MAX_BODY_SIZE:
                response = (
                    "HTTP/1.1 413 Payload Too Large\r\n"
                    "Content-Type: application/json\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                    '{"error": "Request body too large"}'
                ).encode()
                writer.write(response)
                await writer.drain()
                return

            body = await reader.read(content_length) if content_length > 0 else b""

            result, status = await self._dispatch(method, path, body, headers=headers)
            result_bytes = json.dumps(result).encode()
            response = (
                f"HTTP/1.1 {status} OK\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(result_bytes)}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode() + result_bytes
            writer.write(response)
            await writer.drain()
        except Exception:  # noqa: BLE001
            pass

    def build_asgi(self) -> Any:
        """Return a Starlette ASGI app for the active runtime surface.

        Use this in deployment entry-points where the ASGI server (gunicorn,
        uvicorn) is started externally rather than via :meth:`serve`::

            runtime   = LocalRuntime(app, backend_overrides={...})
            application = runtime.build_asgi()   # gunicorn main:application

        Returns:
            A ``starlette.applications.Starlette`` instance wired to
            the mounted ASGI/WSGI app or, when none is mounted, :meth:`_dispatch`.
        """
        try:
            from contextlib import asynccontextmanager

            from starlette.applications import Starlette
            from starlette.middleware.wsgi import WSGIMiddleware
            from starlette.requests import Request as StarletteRequest
            from starlette.responses import JSONResponse
            from starlette.routing import Mount, Route
        except ImportError as exc:
            raise RuntimeError(
                "build_asgi() requires starlette.\n"
                "Install it with:  pip install starlette\n"
                f"Missing: {exc}"
            ) from exc

        @asynccontextmanager
        async def _lifespan(app: Any) -> AsyncIterator[None]:  # noqa: ANN401
            del app
            await self.ensure_started()
            try:
                yield
            finally:
                await self.shutdown()

        async def _handle(request: StarletteRequest) -> JSONResponse:
            body = await request.body()
            result, status = await self._dispatch(
                request.method,
                request.url.path,
                body,
                headers=dict(request.headers.items()),
            )
            return JSONResponse(result, status_code=status)

        async def _health(request: Any) -> JSONResponse:  # noqa: ANN001
            return JSONResponse({"status": "ok", "app": self.app.name})

        async def _ready(request: Any) -> JSONResponse:  # noqa: ANN001
            payload = self._readiness_payload()
            status = 200 if self._readiness_state == "ready" else 503
            return JSONResponse(payload, status_code=status)

        asgi_app = getattr(self.app, "_asgi_app", None)
        wsgi_app = getattr(self.app, "_wsgi_app", None)
        if asgi_app is not None:
            application = Starlette(
                lifespan=_lifespan,
                routes=[
                    Route("/health", _health),
                    Route("/ready", _ready),
                    Route("/_skaal/{path:path}", _handle, methods=["GET", "POST"]),
                    Mount("/", asgi_app),
                ],
            )
            return application

        if wsgi_app is not None:
            application = Starlette(
                lifespan=_lifespan,
                routes=[
                    Route("/health", _health),
                    Route("/ready", _ready),
                    Route("/_skaal/{path:path}", _handle, methods=["GET", "POST"]),
                    Mount("/", WSGIMiddleware(wsgi_app)),
                ],
            )
            return application

        application = Starlette(
            lifespan=_lifespan,
            routes=[
                Route("/", _handle, methods=["GET"]),
                Route("/health", _handle, methods=["GET"]),
                Route("/ready", _handle, methods=["GET"]),
                Route("/{path:path}", _handle, methods=["GET", "POST"]),
            ],
        )
        return application

    async def serve(self) -> None:
        """
        Start the HTTP server and run until cancelled.

        Dispatch order:
        - ASGI app registered via ``app.mount_asgi()`` → :meth:`_serve_asgi`
        - WSGI app registered via ``app.mount_wsgi()`` → :meth:`_serve_wsgi`
        - Otherwise → :meth:`_serve_skaal` (Skaal functions as POST endpoints)
        """
        await self.ensure_started()
        try:
            asgi_app = getattr(self.app, "_asgi_app", None)
            wsgi_app = getattr(self.app, "_wsgi_app", None)
            if asgi_app is not None:
                await self._serve_asgi(asgi_app)
            elif wsgi_app is not None:
                await self._serve_wsgi(wsgi_app)
            else:
                await self._serve_skaal()
        finally:
            await self.shutdown()

    async def _serve_skaal(self) -> None:
        """Expose @app.function() as POST /{name} endpoints via uvicorn + Starlette.

        Also starts an APScheduler ``AsyncIOScheduler`` for any functions
        registered with ``@app.schedule()``.
        """

        try:
            import uvicorn
            from starlette.applications import Starlette
            from starlette.requests import Request as StarletteRequest
            from starlette.responses import JSONResponse
            from starlette.routing import Route
        except ImportError as exc:
            raise RuntimeError(
                "skaal run requires uvicorn and starlette.\n"
                "Install them with:  pip install uvicorn starlette\n"
                f"Missing: {exc}"
            ) from exc

        # ── Print startup banner ───────────────────────────────────────────────
        public_fns = sorted(self._public_functions())
        scheduled = self._collect_schedules()

        banner_lines = [f"  http://{self.host}:{self.port}", ""]
        for name in public_fns:
            banner_lines.append(f"    POST {_SKAAL_INVOKE_PREFIX}{name}")
        if scheduled:
            banner_lines.append("")
            for name, fn in sorted(scheduled.items()):
                meta = fn.__skaal_schedule__
                trigger = meta["trigger"]
                banner_lines.append(f"    schedule /{name}  [{trigger!r}]")
        log.info(_format_banner(f"  Skaal local runtime — {self.app.name}", banner_lines))

        # ── Starlette ASGI app — delegates to existing _dispatch ──────────────
        async def _handle(request: StarletteRequest) -> JSONResponse:
            body = await request.body()
            result, status = await self._dispatch(
                request.method,
                request.url.path,
                body,
                headers=dict(request.headers.items()),
            )
            return JSONResponse(result, status_code=status)

        asgi_app = Starlette(
            routes=[
                Route("/", _handle, methods=["GET"]),
                Route("/health", _handle, methods=["GET"]),
                Route("/ready", _handle, methods=["GET"]),
                Route("/{path:path}", _handle, methods=["GET", "POST"]),
            ]
        )

        # ── Start APScheduler for scheduled functions ──────────────────────────
        scheduler = None
        if scheduled:
            try:
                from skaal.schedule import create_async_scheduler

                scheduler = create_async_scheduler(scheduled, logger=log)

                scheduler.start()
            except ImportError:
                log.warning(
                    "  WARNING: apscheduler not installed — scheduled functions will not run.\n"
                    "           Install with: pip install apscheduler\n"
                )

        try:
            config = uvicorn.Config(asgi_app, host=self.host, port=self.port, log_level="info")
            await uvicorn.Server(config).serve()
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)

    def start_background_scheduler(self) -> None:
        """Start APScheduler in a daemon thread for WSGI / gunicorn deployments.

        ``_serve_skaal`` runs APScheduler inside an asyncio event loop that it
        owns.  When gunicorn serves a WSGI app it never calls ``serve()``, so the
        scheduler would not start.  Call this method from the generated ``main.py``
        (or any gunicorn entry-point) immediately after constructing
        ``LocalRuntime`` to get the same scheduling behaviour::

            runtime = LocalRuntime(app, backend_overrides={...})
            runtime.start_background_scheduler()   # ← add this line
            application = app.dash_app.server

        The thread is daemonised so it does not prevent gunicorn from shutting
        down.  Each scheduled function fires in its own asyncio event loop
        running inside the thread; the ``ScheduleContext.fired_at`` timestamp
        and any errors are printed to stdout so they appear in ``docker logs``.
        """
        import threading

        scheduled = self._collect_schedules()
        if not scheduled:
            return

        def _run() -> None:
            import asyncio as _asyncio

            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)

            try:
                from skaal.schedule import create_async_scheduler
            except ImportError:
                log.warning(
                    "[skaal/scheduler] WARNING: apscheduler not installed"
                    " — scheduled functions will not run.\n"
                    "                  Install with: pip install apscheduler"
                )
                return

            scheduler = create_async_scheduler(
                scheduled,
                event_loop=loop,
                logger=log,
                log_lifecycle=True,
            )

            scheduler.start()
            log.info("[skaal/scheduler] started %s job(s): %s", len(scheduled), list(scheduled))
            loop.run_forever()

        thread = threading.Thread(target=_run, daemon=True, name="skaal-scheduler")
        thread.start()

    def start_background_jobs(self) -> None:
        """Start the jobs worker in a daemon thread for WSGI / gunicorn deployments.

        WSGI artifacts do not call ``serve()``, so delayed jobs would otherwise
        remain idle after container start until something else explicitly starts
        the runtime. This mirrors ``start_background_scheduler()`` for the jobs
        worker path.
        """
        import threading

        if self._background_jobs_thread_started or not self._job_handlers:
            return
        self._background_jobs_thread_started = True

        def _run() -> None:
            import asyncio as _asyncio

            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)

            async def _bootstrap() -> None:
                try:
                    await self.ensure_started()
                    log.info("[skaal/jobs] started background worker for %s", self.app.name)
                except Exception as exc:  # noqa: BLE001
                    log.warning("[skaal/jobs] background worker failed to start: %s", exc)
                    loop.stop()

            loop.create_task(_bootstrap())
            loop.run_forever()

        thread = threading.Thread(target=_run, daemon=True, name="skaal-jobs")
        thread.start()

    async def _serve_wsgi(self, wsgi_app: Any) -> None:
        """
        Serve a WSGI app (Dash/Flask) via uvicorn + starlette WSGIMiddleware.

        Skaal storage is already wired by ``__init__``; this method only
        handles the HTTP layer.  A ``/health`` endpoint is grafted onto the
        starlette router before the WSGI catch-all so that load-balancer
        probes work without touching the Flask app.

        Requires ``uvicorn`` and ``starlette`` — both are in ``skaal[gcp]``
        and can be installed standalone with::

            pip install uvicorn starlette
        """
        try:
            import uvicorn
            from starlette.applications import Starlette
            from starlette.middleware.wsgi import WSGIMiddleware
            from starlette.requests import Request as StarletteRequest
            from starlette.responses import JSONResponse
            from starlette.routing import Mount, Route
        except ImportError as exc:
            raise RuntimeError(
                "Serving a WSGI app locally requires uvicorn and starlette.\n"
                "Install them with:  pip install uvicorn starlette\n"
                f"Missing: {exc}"
            ) from exc

        async def _health(request: Any) -> JSONResponse:  # noqa: ANN001
            return JSONResponse({"status": "ok", "app": self.app.name})

        async def _internal(request: StarletteRequest) -> JSONResponse:
            body = await request.body()
            result, status = await self._dispatch(
                request.method,
                request.url.path,
                body,
                headers=dict(request.headers.items()),
            )
            return JSONResponse(result, status_code=status)

        asgi_app = Starlette(
            routes=[
                Route("/health", _health),
                Route("/ready", _internal, methods=["GET"]),
                Route("/_skaal/{path:path}", _internal, methods=["GET", "POST"]),
                Mount("/", WSGIMiddleware(wsgi_app)),
            ]
        )

        attribute = getattr(self.app, "_wsgi_attribute", "wsgi_app")
        log.info(
            _format_banner(
                f"  Skaal local runtime — {self.app.name}  [WSGI: {attribute}]",
                [
                    f"  http://{self.host}:{self.port}",
                    "",
                    "    /health  → Skaal health check",
                    "    /_skaal/* → Skaal internal invoke endpoints",
                    f"    /*       → {attribute}  (Dash / Flask)",
                ],
            )
        )

        config = uvicorn.Config(
            asgi_app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()

    async def _serve_asgi(self, asgi_app: Any) -> None:
        """
        Serve a native ASGI app (FastAPI, Starlette) directly via uvicorn.

        Unlike WSGI apps, no middleware adapter is needed — the app is passed
        straight to uvicorn.  A ``/health`` endpoint is grafted in front so
        load-balancer probes work without touching the user's app.

        Requires ``uvicorn`` and ``starlette``::

            pip install uvicorn starlette
        """
        try:
            import uvicorn
            from starlette.applications import Starlette
            from starlette.responses import JSONResponse
            from starlette.routing import Mount, Route
        except ImportError as exc:
            raise RuntimeError(
                "Serving an ASGI app locally requires uvicorn and starlette.\n"
                "Install them with:  pip install uvicorn starlette\n"
                f"Missing: {exc}"
            ) from exc

        async def _health(request: Any) -> JSONResponse:  # noqa: ANN001
            return JSONResponse({"status": "ok", "app": self.app.name})

        async def _handle(request: Any) -> JSONResponse:  # noqa: ANN001
            body = await request.body()
            result, status = await self._dispatch(
                request.method,
                request.url.path,
                body,
                headers=dict(request.headers.items()),
            )
            return JSONResponse(result, status_code=status)

        wrapped = Starlette(
            routes=[
                Route("/health", _health),
                Route("/ready", _handle, methods=["GET"]),
                Route("/_skaal/{path:path}", _handle, methods=["GET", "POST"]),
                Mount("/", asgi_app),
            ]
        )

        attribute = getattr(self.app, "_asgi_attribute", "asgi_app")
        log.info(
            _format_banner(
                f"  Skaal local runtime — {self.app.name}  [ASGI: {attribute}]",
                [
                    f"  http://{self.host}:{self.port}",
                    "",
                    "    /health  → Skaal health check",
                    "    /_skaal/* → Skaal internal invoke endpoints",
                    f"    /*       → {attribute}  (FastAPI / Starlette)",
                ],
            )
        )

        config = uvicorn.Config(wrapped, host=self.host, port=self.port, log_level="info")
        await uvicorn.Server(config).serve()
