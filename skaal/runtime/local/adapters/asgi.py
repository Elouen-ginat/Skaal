"""Adapter that mounts user ASGI apps onto the Starlette router."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.types import ASGIApp

if TYPE_CHECKING:
    from skaal.binding.model import PlannedResource
    from skaal.runtime.local.runtime import LocalRuntime


def register(runtime: LocalRuntime, bound: PlannedResource, target: Any) -> None:
    app: Any = runtime.app
    path: str = bound.inferred.overrides.options.get("path", "/")

    mounts: dict[str, ASGIApp] = getattr(app, "_asgi_path_mounts", {}) or {}
    asgi_app: ASGIApp | None = mounts.get(path)
    if asgi_app is None:
        return

    runtime.add_mount(path, asgi_app)
