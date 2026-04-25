from __future__ import annotations

from typing import TYPE_CHECKING, Any


class _LocalServerMixin:
    if TYPE_CHECKING:
        app: Any
        host: str
        port: int
        _function_cache: dict[str, Any]
        _engines: list[Any]

        def _collect_schedules(self) -> dict[str, Any]: ...

        async def _dispatch(self, method: str, path: str, body: bytes) -> tuple[Any, int]: ...

        def _register_schedules(
            self,
            scheduler: Any,
            scheduled: dict[str, Any],
            *,
            log_runs: bool,
        ) -> None: ...

        async def shutdown(self) -> None: ...

    async def _serve_with_starlette(
        self,
        mounted_app: Any,
        *,
        runtime_label: str,
        attribute: str,
        framework_label: str,
        missing_message: str,
    ) -> None:
        try:
            import uvicorn
            from starlette.applications import Starlette
            from starlette.responses import JSONResponse
            from starlette.routing import Mount, Route
        except ImportError as exc:
            raise RuntimeError(
                f"{missing_message}\n"
                "Install them with:  pip install uvicorn starlette\n"
                f"Missing: {exc}"
            ) from exc

        async def _health(request: Any) -> JSONResponse:  # noqa: ANN001
            return JSONResponse({"status": "ok", "app": self.app.name})

        wrapped = Starlette(
            routes=[
                Route("/health", _health),
                Mount("/", mounted_app),
            ]
        )

        print(f"\n  Skaal local runtime — {self.app.name}  [{runtime_label}: {attribute}]")
        print(f"  http://{self.host}:{self.port}\n")
        print("    /health  → Skaal health check")
        print(f"    /*       → {attribute}  ({framework_label})")
        print()

        config = uvicorn.Config(wrapped, host=self.host, port=self.port, log_level="info")
        await uvicorn.Server(config).serve()

    def build_asgi(self) -> Any:
        """Return a Starlette ASGI app that serves all ``@app.function()`` endpoints.

        Use this in deployment entry-points where the ASGI server (gunicorn,
        uvicorn) is started externally rather than via :meth:`serve`::

            runtime   = LocalRuntime(app, backend_overrides={...})
            application = runtime.build_asgi()   # gunicorn main:application

        Returns:
            A ``starlette.applications.Starlette`` instance wired to
            :meth:`_dispatch`.
        """
        try:
            from starlette.applications import Starlette
            from starlette.requests import Request as StarletteRequest
            from starlette.responses import JSONResponse
            from starlette.routing import Route
        except ImportError as exc:
            raise RuntimeError(
                "build_asgi() requires starlette.\n"
                "Install it with:  pip install starlette\n"
                f"Missing: {exc}"
            ) from exc

        async def _handle(request: StarletteRequest) -> JSONResponse:
            body = await request.body()
            result, status = await self._dispatch(request.method, request.url.path, body)
            return JSONResponse(result, status_code=status)

        return Starlette(
            routes=[
                Route("/", _handle, methods=["GET"]),
                Route("/health", _handle, methods=["GET"]),
                Route("/{path:path}", _handle, methods=["GET", "POST"]),
            ]
        )

    async def serve(self) -> None:
        """
        Start the HTTP server and run until cancelled.

        Dispatch order:
        - ASGI app registered via ``app.mount_asgi()`` → :meth:`_serve_asgi`
        - WSGI app registered via ``app.mount_wsgi()`` → :meth:`_serve_wsgi`
        - Otherwise → :meth:`_serve_skaal` (Skaal functions as POST endpoints)
        """
        await self._start_engines()
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

    async def _start_engines(self) -> None:
        """Spin up all pattern engines (EventLog / Projection / Saga / Outbox)."""
        from skaal.runtime.engines import start_engines_for

        self._engines = await start_engines_for(self.app, self)

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

        funcs = self._function_cache
        public_fns = [n for n in sorted(funcs) if not hasattr(funcs[n], "__skaal_schedule__")]
        scheduled = self._collect_schedules()

        print(f"\n  Skaal local runtime — {self.app.name}")
        print(f"  http://{self.host}:{self.port}\n")
        for name in public_fns:
            print(f"    POST /{name}")
        if scheduled:
            print()
            for name, fn in sorted(scheduled.items()):
                meta = fn.__skaal_schedule__
                trigger = meta["trigger"]
                print(f"    schedule /{name}  [{trigger!r}]")
        print()

        async def _handle(request: StarletteRequest) -> JSONResponse:
            body = await request.body()
            result, status = await self._dispatch(request.method, request.url.path, body)
            return JSONResponse(result, status_code=status)

        asgi_app = Starlette(
            routes=[
                Route("/", _handle, methods=["GET"]),
                Route("/health", _handle, methods=["GET"]),
                Route("/{path:path}", _handle, methods=["GET", "POST"]),
            ]
        )

        scheduler = None
        if scheduled:
            try:
                from apscheduler.schedulers.asyncio import AsyncIOScheduler

                scheduler = AsyncIOScheduler()
                self._register_schedules(scheduler, scheduled, log_runs=False)
                scheduler.start()
            except ImportError:
                print(
                    "  WARNING: apscheduler not installed — scheduled functions will not run.\n"
                    "           Install with: pip install apscheduler\n"
                )

        try:
            config = uvicorn.Config(asgi_app, host=self.host, port=self.port, log_level="info")
            await uvicorn.Server(config).serve()
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)

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
            from starlette.middleware.wsgi import WSGIMiddleware
        except ImportError as exc:
            raise RuntimeError(
                "Serving a WSGI app locally requires uvicorn and starlette.\n"
                "Install them with:  pip install uvicorn starlette\n"
                f"Missing: {exc}"
            ) from exc

        await self._serve_with_starlette(
            WSGIMiddleware(wsgi_app),
            runtime_label="WSGI",
            attribute=getattr(self.app, "_wsgi_attribute", "wsgi_app"),
            framework_label="Dash / Flask",
            missing_message="Serving a WSGI app locally requires uvicorn and starlette.",
        )

    async def _serve_asgi(self, asgi_app: Any) -> None:
        """
        Serve a native ASGI app (FastAPI, Starlette) directly via uvicorn.

        Unlike WSGI apps, no middleware adapter is needed — the app is passed
        straight to uvicorn.  A ``/health`` endpoint is grafted in front so
        load-balancer probes work without touching the user's app.

        Requires ``uvicorn`` and ``starlette``::

            pip install uvicorn starlette
        """
        await self._serve_with_starlette(
            asgi_app,
            runtime_label="ASGI",
            attribute=getattr(self.app, "_asgi_attribute", "asgi_app"),
            framework_label="FastAPI / Starlette",
            missing_message="Serving an ASGI app locally requires uvicorn and starlette.",
        )
