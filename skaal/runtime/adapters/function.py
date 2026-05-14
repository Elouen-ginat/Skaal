"""Adapter that exposes `@app.function` callables as HTTP routes.

The route shape is ``POST /<bare_name>`` with a JSON request body. The
body is passed as ``**kwargs`` to the wrapped callable (consistent with
`Module.invoke(name, **kwargs)`). Errors propagate as 500s; the deploy
layer will reshape this contract once API Gateway / Lambda wiring lands.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from skaal.runtime.middleware import wrap_resilience

if TYPE_CHECKING:
    from skaal.binding.model import BoundResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: BoundResource, target: Any) -> None:
    """Wire ``target`` (the user's callable) onto the runtime as a route."""
    if bound.external:
        # External functions are not provisioned and not routed; the user
        # is expected to invoke them through `Environment.backends[...]`.
        return

    metadata = getattr(target, "__skaal_function__", None) or {}
    handler = _coerce_async(target)
    wrapped = wrap_resilience(
        handler,
        retry=metadata.get("retry"),
        circuit_breaker=metadata.get("circuit_breaker"),
        rate_limit=metadata.get("rate_limit"),
        bulkhead=metadata.get("bulkhead"),
    )

    bare = bound.inferred.id.split(":")[-1].split(".")[-1]
    path = f"/{bare}"

    async def endpoint(request: Any) -> Any:
        from starlette.responses import JSONResponse

        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {"value": payload}
        try:
            result = await wrapped(**payload)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
        return JSONResponse({"result": _to_jsonable(result)})

    runtime.add_route(path, endpoint, method="POST")


def _coerce_async(fn: Any) -> Any:
    """Return an awaitable wrapper for ``fn`` even if it's a sync callable."""
    if inspect.iscoroutinefunction(fn):
        return fn

    # FunctionRef proxies through __call__ to the wrapped coroutine; check
    # the wrapped object directly rather than poking at dunders ruff flags.
    wrapped = getattr(fn, "__wrapped__", None)
    if wrapped is not None and inspect.iscoroutinefunction(wrapped):
        return fn

    async def _wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    return _wrapper


def _to_jsonable(value: Any) -> Any:
    """Best-effort JSON projection for handler return values."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value
