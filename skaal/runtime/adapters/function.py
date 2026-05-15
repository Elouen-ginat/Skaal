"""Adapter that exposes `@app.function` callables as HTTP routes.

For regular coroutine functions the adapter both:

* Adds a ``POST /<bare_name>`` Starlette route whose JSON body is
  spread as ``**kwargs`` to the resilience-wrapped callable.
* Registers the same wrapped callable in
  `runtime.state.invokables` so `Module.invoke(...)` dispatches
  through the identical chain without round-tripping HTTP.

For async-generator functions (``async def fn(): yield ...``) the
adapter only populates `runtime.state.invokable_streams` — the HTTP
route would have to be SSE-shaped and that wiring is its own work
item. Users surface streams via their mounted FastAPI / Starlette
routes plus `app.invoke_stream(...)`.

Errors on the HTTP path propagate as 500s; the deploy layer will
reshape this contract once API Gateway / Lambda wiring lands.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from skaal.runtime.middleware import wrap_resilience
from skaal.types.compute import ResiliencePolicies

if TYPE_CHECKING:
    from skaal.binding.model import BoundResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: BoundResource, target: Any) -> None:
    """Wire ``target`` (the user's callable) onto the runtime."""
    if bound.external:
        # External functions are not provisioned and not routed; the user
        # is expected to invoke them through `Environment.backends[...]`.
        return

    bare: str = bound.inferred.source.bare_name
    # `Module._resolve_invokable` returns the `<app.name>.<bare>` form
    # built by `_collect_all`; the in-process invokable registries must
    # be keyed the same way so `runtime.invoke(name, ...)` finds the
    # entry.
    qualified: str = f"{runtime.app.name}.{bare}" if runtime.app.name else bare

    underlying: Any = getattr(target, "__wrapped__", target)
    if inspect.isasyncgenfunction(underlying):
        # Streams skip the resilience chain (retry on a partial stream
        # is ill-defined) and skip the HTTP route. Users wrap the
        # iterator in a Starlette `StreamingResponse` themselves via
        # `app.invoke_stream(...)`.
        stream_handler: Callable[..., AsyncIterator[Any]] = underlying
        runtime.state.invokable_streams[qualified] = stream_handler
        return

    policies: ResiliencePolicies = (
        bound.inferred.overrides.resilience or ResiliencePolicies()
    )
    handler: Callable[..., Awaitable[Any]] = _coerce_async(target)
    wrapped: Callable[..., Awaitable[Any]] = wrap_resilience(
        handler,
        retry=policies.retry,
        circuit_breaker=policies.circuit_breaker,
        rate_limit=policies.rate_limit,
        bulkhead=policies.bulkhead,
    )

    runtime.state.invokables[qualified] = wrapped

    path: str = f"/{bare}"

    async def endpoint(request: Request) -> JSONResponse:
        payload: Any
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {"value": payload}
        try:
            result: Any = await wrapped(**payload)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
        return JSONResponse({"result": _to_jsonable(result)})

    runtime.add_route(path, endpoint, method="POST")


def _coerce_async(fn: Any) -> Callable[..., Awaitable[Any]]:
    """Return an awaitable wrapper for ``fn`` even if it's a sync callable."""
    if inspect.iscoroutinefunction(fn):
        return fn

    # FunctionRef proxies through __call__ to the wrapped coroutine; check
    # the wrapped object directly rather than poking at dunders ruff flags.
    wrapped_attr: Any = getattr(fn, "__wrapped__", None)
    if wrapped_attr is not None and inspect.iscoroutinefunction(wrapped_attr):
        return fn

    async def _wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    return _wrapper


def _to_jsonable(value: Any) -> Any:
    """Best-effort JSON projection for handler return values."""
    model_dump: Callable[..., Any] | None = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return value
