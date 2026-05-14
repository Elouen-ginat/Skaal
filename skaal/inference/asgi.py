"""Recogniser for ASGI/WSGI sub-applications mounted on an `App`.

Two surfaces are recognised (ADR 028 §6.4.1, ADR 030 §2.4, ADR 032 §4.6):

- The legacy ``app.mount_asgi(...)`` / ``app.mount_wsgi(...)`` aliases,
  which set ``_asgi_app`` / ``_wsgi_app`` on the `App` instance. One
  combined ``ASGI_SERVICE`` resource is emitted when either is set.
- The path-form ``app.mount("/path", asgi_app)`` (ADR 028 §6.4.1) which
  populates ``_asgi_path_mounts: dict[str, ASGIApplication]``. One
  ``ASGI_SERVICE`` resource is emitted per mount path; the path itself
  rides on ``InferredResource.overrides.options["path"]``.

The legacy surface continues to be recognised until the runtime rewire
deletes ``mount_asgi`` / ``mount_wsgi``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from skaal.inference.model import (
    InferredResource,
    ResourceKind,
    ResourceOverrides,
    SourceLocation,
)

if TYPE_CHECKING:
    from skaal.app import App


def recognise_mount(app: App) -> InferredResource | None:
    """Return one combined ``ASGI_SERVICE`` resource for the legacy mounts."""
    asgi_app = getattr(app, "_asgi_app", None)
    asgi_attribute = getattr(app, "_asgi_attribute", None)
    wsgi_app = getattr(app, "_wsgi_app", None)
    wsgi_attribute = getattr(app, "_wsgi_attribute", None)

    if asgi_app is None and wsgi_app is None and asgi_attribute is None and wsgi_attribute is None:
        return None

    attribute = asgi_attribute or wsgi_attribute or app.name
    resource_id = f"{app.__class__.__module__}:{app.name}.mount({attribute})"
    return InferredResource(
        id=resource_id,
        kind=ResourceKind.ASGI_SERVICE,
        source=SourceLocation.from_object(app.__class__),
    )


def recognise_path_mounts(app: App) -> list[InferredResource]:
    """Return one ``ASGI_SERVICE`` resource per ``App.mount(path, asgi_app)`` entry.

    Phase 4's path-form (ADR 028 §6.4.1) is recognised independently of the
    legacy ``mount_asgi`` / ``mount_wsgi`` aliases — both can coexist on the
    same `App` until the legacy surface is deleted. The mount path is carried
    on ``InferredResource.overrides.options["path"]`` so the deploy layer can
    wire one API Gateway route per mount.
    """
    path_mounts: dict[str, object] = getattr(app, "_asgi_path_mounts", {}) or {}
    resources: list[InferredResource] = []
    for path in sorted(path_mounts):
        resource_id = f"{app.__class__.__module__}:{app.name}.mount({path})"
        resources.append(
            InferredResource(
                id=resource_id,
                kind=ResourceKind.ASGI_SERVICE,
                source=SourceLocation.from_object(app.__class__),
                overrides=ResourceOverrides(options={"path": path}),
            )
        )
    return resources
