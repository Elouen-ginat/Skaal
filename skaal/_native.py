"""Helper for the typed `.native()` escape on the four primitives (ADR 028 §6.13).

`Store` / `BlobStore` / `Table` / `Topic` all expose a `.native()`
hook that resolves to the wired backend's native SDK client. The common shape is the same: when the
backend exposes its own `.native()` callable, unwrap it (await if it
returns an awaitable); otherwise return the backend object itself.

Phase 5b deferred work narrows the return type via per-token overload
pairs so `await Cache.native()` reveals the concrete SDK type. Phase 5a
ships `Any` from this helper so the runtime is in place ahead of the
strict-typing sweep.
"""

from __future__ import annotations

import inspect
from typing import Any


async def resolve_native(backend: Any) -> Any:
    """Return the native SDK client for *backend* (Phase 5a contract).

    The same dispatch is shared by every primitive's `.native()`
    classmethod so the typing-contract test surface only has to cover
    one code path. Backends that ship their own `.native()` are
    unwrapped (including awaitable form); otherwise the backend object
    is returned directly so user-land can introspect or call into it.
    """
    backend_native = getattr(backend, "native", None)
    if callable(backend_native):
        result: Any = backend_native()
        if inspect.isawaitable(result):
            return await result
        return result
    return backend
