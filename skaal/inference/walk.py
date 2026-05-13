"""Walk an `App` into a deterministic `InferredPlan`.

Single public function: ``infer(app) -> InferredPlan``. The walker collects
resources from the `Module` registry buckets and the `App`-level mount
attributes, deduplicates by ``id(obj)``, sorts by ``(kind, id)``, and
finalises the plan with a fingerprint.

See ADR 030 §2.2 for the design.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from skaal.inference.asgi import recognise_mount
from skaal.inference.fingerprint import fingerprint_plan
from skaal.inference.model import InferredPlan, InferredResource

if TYPE_CHECKING:
    from skaal.app import App
    from skaal.module import Module


_INFERRED_ATTR = "__skaal_inferred__"


def infer(app: App) -> InferredPlan:
    """Walk ``app`` and return its `InferredPlan`.

    Resources are collected from the module's storage / functions / jobs /
    channels / schedules buckets, plus an optional ``ASGI_SERVICE`` resource
    if the app has mounted a WSGI or ASGI sub-application. Edges are not
    emitted in Phase 2 (`InferredPlan.edges` is always empty); the bytecode
    call-graph walker that fills them lands in Phase 6.
    """
    seen: dict[int, InferredResource] = {}

    for obj in _iter_registered(app):
        resource = getattr(obj, _INFERRED_ATTR, None)
        if resource is None or not isinstance(resource, InferredResource):
            continue
        seen.setdefault(id(obj), resource)

    asgi_resource = recognise_mount(app)
    if asgi_resource is not None:
        seen[id(app)] = asgi_resource

    resources = tuple(sorted(seen.values(), key=lambda r: (r.kind.value, r.id)))
    plan = InferredPlan(app=app.name, resources=resources, edges=())
    return plan.with_fingerprint(fingerprint_plan(plan))


def _iter_registered(module: Module) -> list[object]:
    """Yield every registered object in ``module`` and its submodules.

    Submodule traversal follows the existing `Module._collect_all` semantics:
    every storage, function, job, channel, and schedule registered on a
    submodule is included, regardless of export status — the inference layer
    sees the full graph, not the namespaced subset that runtime clients see.
    """
    out: list[object] = []
    out.extend(module._storage.values())
    out.extend(module._functions.values())
    out.extend(module._jobs.values())
    out.extend(module._channels.values())
    out.extend(module._schedules.values())

    for sub in module._submodules.values():
        out.extend(_iter_registered(sub))

    return out
