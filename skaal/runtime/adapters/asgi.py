"""Adapter that mounts user ASGI apps onto the Starlette router.

The inference layer emits one `ASGI_SERVICE` resource per path mounted
via `app.mount("/path", asgi_app)`. The adapter reads the path from
``InferredResource.overrides.options["path"]`` and registers a mount on
the runtime.

The legacy `mount_asgi` / `mount_wsgi` aliases populate the resource
with a single root mount (path ``"/"``); they continue to work until
the runtime rewire completes the deletion called out in ADR 032 §4.6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skaal.binding.model import BoundResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: BoundResource, target: Any) -> None:
    """Mount the user's ASGI app under the path declared on the resource."""
    app = runtime.app
    path = bound.inferred.overrides.options.get("path", "/")

    asgi_app = _resolve_asgi_app(app, path)
    if asgi_app is None:
        # Without a live ASGI app there is nothing to serve locally —
        # the deploy layer will still synthesise an API Gateway route.
        return

    runtime.add_mount(path, asgi_app)


def _resolve_asgi_app(app: Any, path: str) -> Any:
    mounts: dict[str, Any] = getattr(app, "_asgi_path_mounts", {}) or {}
    if path in mounts:
        return mounts[path]
    if path == "/":
        asgi_app = getattr(app, "_asgi_app", None)
        if asgi_app is not None:
            return asgi_app
        wsgi_app = getattr(app, "_wsgi_app", None)
        if wsgi_app is not None:
            from starlette.middleware.wsgi import WSGIMiddleware

            return WSGIMiddleware(wsgi_app)
    return None
