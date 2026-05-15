"""Adapter that exposes `@app.function` callables as HTTP routes.

The route shape is ``POST /<bare_name>`` with a JSON request body. The
body is passed as ``**kwargs`` to the wrapped callable (consistent with
`Module.invoke(name, **kwargs)`). Errors propagate as 500s; the deploy
layer will reshape this contract once API Gateway / Lambda wiring lands.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from skaal.runtime.middleware import wrap_resilience
from skaal.types.compute import ResiliencePolicies

if TYPE_CHECKING:
    from skaal.binding.model import BoundResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: BoundResource, target: Any) -> None:
    """Wire ``target`` (the user's callable) onto the runtime as a route."""
    if bound.external:
        # External functions are not provisioned and not routed; the user
        # is expected to invoke them through `Environment.backends[...]`.
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

    bare: str = bound.inferred.id.split(":")[-1].split(".")[-1]
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
