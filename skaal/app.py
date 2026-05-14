"""App — the central registry for a Skaal application."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar, overload

from skaal.module import Module, ModuleExport

if TYPE_CHECKING:
    from skaal.inference import InferredPlan

F = TypeVar("F", bound=Callable[..., Any])


class App(Module):
    """
    Central registry for a Skaal application.

    `App` extends `Module` with HTTP mounting via `mount()`. All storage,
    agent, function, channel, pattern, and attach methods are inherited from
    `Module`.

    Deployment target and region are environment concerns. They are passed to
    `skaal deploy` via CLI flags or environment variables (`SKAAL_TARGET`,
    `SKAAL_REGION`), not declared in application code. Scaling policy
    (min/max instances, concurrency) lives in the catalog's
    `[compute.X.deploy]` section so it can be overridden per environment
    without touching source code.

    Examples:

        app = App("my-service")

        @app.storage(read_latency="< 5ms", durability="persistent")
        class Profiles(Store[Profile]):
            pass

        @app.function()
        async def predict(customer_id: str) -> float:
            ...
    """

    # ── WSGI app mounting ──────────────────────────────────────────────────

    def mount_wsgi(self, wsgi_app: Any | None = None, *, attribute: str) -> None:
        """
        Register an external WSGI application to be served by this Skaal app.

        Args:
            wsgi_app:  The WSGI callable itself (e.g. ``dash_app.server``).
                       Pass `None` if only generating deploy artifacts without
                       a running Dash/Flask instance (e.g. Dash not installed).
            attribute: Dotted attribute path in the source module used by the
                       deploy generators to reference the WSGI app in generated
                       entry-point files, e.g. `"dash_app.server"`.

        `skaal run` uses *wsgi_app* directly and serves it via uvicorn plus
        starlette `WSGIMiddleware`, so the full Dash/Flask UI is available at
        `http://localhost:<port>`.

        `skaal deploy` uses *attribute* to generate the correct entry point:

        - Cloud Run: `main.py` with gunicorn serving `application`
        - Lambda: `handler.py` with `Mangum` wrapping the WSGI app

        Examples:

            import dash
            from skaal import App, Store

            app = App("dashboard")

            @app.storage(read_latency="< 5ms", durability="ephemeral", retention="30m")
            class Sessions(Store[dict]):
                pass

            dash_app = dash.Dash(__name__)
            app.mount_wsgi(dash_app.server, attribute="dash_app.server")

            # In Dash callbacks:
            @dash_app.callback(...)
            def update(session_id):
                state = Sessions.sync_get(session_id)
                Sessions.sync_set(session_id, state)
                return result
        """
        self._wsgi_app: Any | None = wsgi_app
        self._wsgi_attribute: str = attribute

    def mount_asgi(self, asgi_app: Any | None = None, *, attribute: str) -> None:
        """
        Register a native ASGI application (FastAPI, Starlette) to be served by
        this Skaal app.

        Prefer this over `mount_wsgi()` for ASGI-native frameworks. No
        `WSGIMiddleware` adapter is needed, so you get full HTTP/2 and
        WebSocket support.

        Args:
            asgi_app:  The ASGI callable (e.g. `fastapi_app`).
                       Pass `None` when generating deploy artifacts without a
                       live instance.
            attribute: Dotted attribute path used by deploy generators in the
                       generated entry-point files, e.g. `"fastapi_app"`.

        Examples:

            from fastapi import FastAPI
            from skaal import App, Store

            skaal_app = App("api")

            @skaal_app.storage(read_latency="< 10ms", durability="persistent")
            class Items(Store[Item]):
                pass

            fastapi_app = FastAPI()

            @fastapi_app.get("/items/{item_id}")
            async def get_item(item_id: str):
                return await Items.get(item_id)

            skaal_app.mount_asgi(fastapi_app, attribute="fastapi_app")
        """
        self._asgi_app: Any | None = asgi_app
        self._asgi_attribute: str = attribute

    # ── Mounting (modules and ASGI apps) ───────────────────────────────────

    @overload
    def mount(self, target: Module, *, prefix: str) -> ModuleExport: ...

    @overload
    def mount(self, target: str, asgi_app: Any) -> None: ...

    def mount(
        self,
        target: Module | str,
        asgi_app: Any | None = None,
        *,
        prefix: str | None = None,
    ) -> ModuleExport | None:
        """
        Mount either a `Module` under a URL prefix, or an ASGI app at a path.

        Two forms are supported (dispatched on the first arg's type):

        - ``app.mount(module, prefix="/api")`` — embed a `Module` and map
          its HTTP-serving functions under a URL prefix. Returns a
          `ModuleExport`.
        - ``app.mount("/api", asgi_app)`` — mount an ASGI application at
          a URL path (ADR 028 §6.4.1, ADR 032 §4.6). The inference layer
          emits one ``ASGI_SERVICE`` resource per path.

        The path-form is additive in Phase 4; the existing
        ``mount_asgi`` / ``mount_wsgi`` aliases continue to work until
        the runtime rewire deletes them.
        """
        if isinstance(target, str):
            if asgi_app is None:
                raise ValueError(
                    "app.mount(path, asgi_app) requires a non-None asgi_app; "
                    "pass the ASGI callable positionally as the second arg."
                )
            if not target.startswith("/"):
                raise ValueError(
                    f"mount path must start with '/': {target!r}"
                )
            if target == "/_skaal" or target.startswith("/_skaal/"):
                raise ValueError("The /_skaal prefix is reserved for Skaal runtime endpoints")
            if not hasattr(self, "_asgi_path_mounts"):
                self._asgi_path_mounts: dict[str, Any] = {}
            if target in self._asgi_path_mounts:
                raise ValueError(f"path already mounted: {target!r}")
            self._asgi_path_mounts[target] = asgi_app
            return None

        if prefix is None:
            raise TypeError(
                "app.mount(module, prefix=...) requires the prefix keyword arg."
            )
        normalized = prefix if prefix.startswith("/") else f"/{prefix}"
        if normalized == "/_skaal" or normalized.startswith("/_skaal/"):
            raise ValueError("The /_skaal prefix is reserved for Skaal runtime endpoints")
        exports = self.use(target)
        ns = exports.namespace or target.name
        if not hasattr(self, "_mounts"):
            self._mounts: dict[str, str] = {}
        self._mounts[ns] = normalized
        return exports

    # ── Inference ──────────────────────────────────────────────────────────

    def infer(self) -> InferredPlan:
        """Walk this app and return its `InferredPlan`.

        The inference layer is the input to the binding layer (Phase 3, see
        ADR 028 §6.2); each call walks the live module graph, so adding a
        resource at runtime is reflected in the next `infer()` result.
        """
        from skaal.inference import infer as _infer

        return _infer(self)

    # ── Introspection ──────────────────────────────────────────────────────

    def describe(self) -> dict[str, Any]:
        base = super().describe()
        base["mounts"] = getattr(self, "_mounts", {})
        return base

    def __repr__(self) -> str:
        return (
            f"App({self.name!r}, "
            f"storage={list(self._storage)}, "
            f"functions={list(self._functions)})"
        )
