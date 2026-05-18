"""Walk an `App` into a deterministic `Blueprint`.

Single public function: ``blueprint(app) -> Blueprint``. The walker collects
resources from the `Module` registry buckets and the `App`-level mount
attributes, deduplicates by ``id(obj)``, sorts by ``(kind, id)``, and
finalises the plan with a fingerprint.

See ADR 030 §2.2 for the design.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from skaal.inference.asgi import recognise_path_mounts
from skaal.inference.fingerprint import fingerprint_plan
from skaal.inference.model import Blueprint, BlueprintResource

if TYPE_CHECKING:
    from skaal.app import App
    from skaal.module import Module


_INFERRED_ATTR = "__skaal_inferred__"


def blueprint(app: App) -> Blueprint:
    """Walk ``app`` and return its `Blueprint`.

    Resources are collected from the module's storage / functions / jobs /
    channels / schedules buckets, plus one ``ASGI_SERVICE`` resource per
    `App.mount(path, asgi_app)` entry. Edges are not emitted in Phase 2
    (`Blueprint.edges` is always empty); the bytecode call-graph walker
    that fills them lands in Phase 6.
    """
    seen: dict[int, BlueprintResource] = {}

    for obj in _iter_registered(app):
        resource = getattr(obj, _INFERRED_ATTR, None)
        if resource is None or not isinstance(resource, BlueprintResource):
            continue
        seen.setdefault(id(obj), resource)

    extra: list[BlueprintResource] = list(recognise_path_mounts(app))

    resources = tuple(
        sorted(
            [*seen.values(), *extra],
            key=lambda r: (r.kind.value, r.id),
        )
    )
    plan = Blueprint(app=app.name, resources=resources, edges=())
    return plan.with_fingerprint(fingerprint_plan(plan))


def _iter_registered(module: Module) -> list[object]:
    """Yield every registered object in ``module`` and its submodules.

    Submodule traversal follows the existing `Module._collect_all` semantics:
    every storage, function, job, channel, and schedule registered on a
    submodule is included, regardless of export status — the inference layer
    sees the full graph, not the namespaced subset that runtime clients see.
    """
    module._autodiscover_declarations()
    out: list[object] = []
    out.extend(module._storage.values())
    out.extend(module._functions.values())
    out.extend(module._jobs.values())
    out.extend(module._channels.values())
    out.extend(module._schedules.values())

    for sub in module._submodules.values():
        out.extend(_iter_registered(sub))

    return out
