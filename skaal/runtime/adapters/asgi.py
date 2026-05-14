"""Adapter that mounts user ASGI apps onto the Starlette router.

The inference layer emits one `ASGI_SERVICE` resource per path mounted
via `app.mount("/path", asgi_app)`. The adapter reads the path from
``InferredResource.overrides.options["path"]`` and registers a mount on
the runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.types import ASGIApp

if TYPE_CHECKING:
    from skaal.binding.model import BoundResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: BoundResource, target: Any) -> None:
    """Mount the user's ASGI app under the path declared on the resource."""
    app: Any = runtime.app
    path: str = bound.inferred.overrides.options.get("path", "/")

    mounts: dict[str, ASGIApp] = getattr(app, "_asgi_path_mounts", {}) or {}
    asgi_app: ASGIApp | None = mounts.get(path)
    if asgi_app is None:
        # Without a live ASGI app there is nothing to serve locally —
        # the deploy layer will still synthesise an API Gateway route.
        return

    runtime.add_mount(path, asgi_app)
