"""Recogniser for ASGI sub-applications mounted on an `App`.

The canonical surface is ``app.mount("/path", asgi_app)`` (ADR 028
§6.4.1, ADR 032 §4.6). The recogniser walks ``app._asgi_path_mounts``
and emits one ``ASGI_SERVICE`` resource per mount path; the path itself
rides on ``InferredResource.overrides.options["path"]`` so the deploy
layer can wire one API Gateway route per mount.

WSGI support is opt-in at the call site: users wrap their WSGI app with
`starlette.middleware.wsgi.WSGIMiddleware` (or `asgiref.WSGIMiddleware`)
before passing it to `mount`. There is no legacy ``mount_asgi`` /
``mount_wsgi`` surface in Phase 4 onwards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from skaal.inference.model import (
    BlueprintResource,
    Overrides,
    ResourceKind,
    SourceLocation,
)

if TYPE_CHECKING:
    from skaal.app import App


def recognise_path_mounts(app: App) -> list[BlueprintResource]:
    """Return one ``ASGI_SERVICE`` resource per ``App.mount(path, asgi_app)`` entry."""
    path_mounts: dict[str, object] = getattr(app, "_asgi_path_mounts", {}) or {}
    resources: list[BlueprintResource] = []
    for path in sorted(path_mounts):
        resource_id = f"{app.__class__.__module__}:{app.name}.mount({path})"
        resources.append(
            BlueprintResource(
                id=resource_id,
                kind=ResourceKind.ASGI_SERVICE,
                source=SourceLocation.from_object(app.__class__),
                overrides=Overrides(options={"path": path}),
            )
        )
    return resources
