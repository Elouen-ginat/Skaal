"""Recogniser for `app.mount_asgi(...)` / `app.mount_wsgi(...)` call-sites.

Phase 4 reshapes `App.mount` to the canonical ``(path, asgi_app)`` form
(ADR 028 §6.4.1). Until then, the inference walker recognises the existing
``mount_asgi`` / ``mount_wsgi`` surfaces by inspecting the attributes those
methods set on the `App` instance.

See ADR 030 §2.4 for the design.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from skaal.inference.model import InferredResource, ResourceKind, SourceLocation

if TYPE_CHECKING:
    from skaal.app import App


def recognise_mount(app: App) -> InferredResource | None:
    """Return an ``ASGI_SERVICE`` resource if ``app`` mounts an ASGI/WSGI app.

    ``None`` is returned when neither a WSGI nor ASGI app has been mounted on
    ``app``. WSGI apps are recognised too — the deploy layer wraps them in
    ``WSGIMiddleware`` for serving; the inference distinction would only
    matter at deploy time, which is Phase 4's concern.
    """
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
