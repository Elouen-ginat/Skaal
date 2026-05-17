"""The local runtime that executes a `BoundPlan`.

The runtime accepts the output of `bind(plan, env, lock)` and runs every
`BoundResource` in-process: storage and channels become live backend
clients, `@app.function` callables get HTTP routes on a Starlette router,
schedules register with APScheduler, and ASGI mounts splice into the
router under their declared paths.

Phase 4 (ADR 032) is the first cut of this rebuild. The current shape is
a working skeleton with first-class adapters for the kinds the local
defaults table emits (`STORE`, `FUNCTION`, `ASGI_SERVICE`, `SECRET`).
The remaining adapters (`RELATIONAL`, `BLOB`, `CHANNEL`, `SCHEDULE`,
`JOB`) raise `NotImplementedError` with a clear pointer; they land in
the same phase as the wider examples sweep.
"""

from __future__ import annotations

from typing import Any

__all__ = ["LocalRuntime", "serve"]


def __getattr__(name: str) -> Any:
    if name in {"LocalRuntime", "serve"}:
        from skaal.runtime.local import LocalRuntime, serve

        exports = {"LocalRuntime": LocalRuntime, "serve": serve}
        return exports[name]
    raise AttributeError(name)
