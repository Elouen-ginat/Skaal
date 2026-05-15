"""App — the central registry for a Skaal application."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar, overload

from skaal.module import Module, ModuleExport

if TYPE_CHECKING:
    from skaal.inference import InferredPlan

F = TypeVar("F", bound=Callable[..., Any])


class App(Module):
    """Central registry for a Skaal application.

    `App` extends `Module` with HTTP mounting via `mount()`. Storage,
    function, channel, schedule, job, and attach methods are inherited
    from `Module`. Deployment target and region are environment concerns
    bound through `skaal.toml` and the binding layer (ADR 028 §6.3); they
    are not declared in application code.

    Examples:

        app = App("my-service")

        @app.storage()
        class Profiles(Store[Profile]):
            pass

        @app.function()
        async def predict(customer_id: str) -> float:
            ...
    """

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
        """Mount either a `Module` under a URL prefix or an ASGI app at a path.

        Two forms are supported (dispatched on the first arg's type):

        - ``app.mount(module, prefix="/api")`` — embed a `Module` and map
          its HTTP-serving functions under a URL prefix. Returns a
          `ModuleExport`.
        - ``app.mount("/api", asgi_app)`` — mount an ASGI application at
          a URL path (ADR 028 §6.4.1, ADR 032 §4.6). The inference layer
          emits one ``ASGI_SERVICE`` resource per path.

        WSGI users wrap their app with `starlette.middleware.wsgi.WSGIMiddleware`
        (or `asgiref.WSGIMiddleware`) at the call site:

            app.mount("/", WSGIMiddleware(dash_app.server))
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
