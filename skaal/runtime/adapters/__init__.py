"""Per-`ResourceKind` adapter modules for the local runtime.

Each adapter exposes a single ``register(runtime, bound, target)``
callable. The dispatch table in `skaal.runtime.dispatch` selects the
adapter; the runtime calls it once per `BoundResource`.

There is no abstract base — adapters are duck-typed.
"""
