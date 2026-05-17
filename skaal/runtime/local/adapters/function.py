"""Adapter that exposes `@app.function` callables as HTTP routes."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from skaal.runtime.local.middleware import wrap_resilience
from skaal.types.compute import ResiliencePolicies

if TYPE_CHECKING:
    from skaal.binding.model import PlannedResource
    from skaal.runtime.local.runtime import LocalRuntime


def register(runtime: LocalRuntime, bound: PlannedResource, target: Any) -> None:
    if bound.external:
        return

    bare: str = bound.inferred.source.bare_name
    qualified: str = f"{runtime.app.name}.{bare}" if runtime.app.name else bare

    underlying: Any = getattr(target, "__wrapped__", target)
    if inspect.isasyncgenfunction(underlying):
        stream_handler: Callable[..., AsyncIterator[Any]] = underlying
        runtime.state.invokable_streams[qualified] = stream_handler
        return

    policies: ResiliencePolicies = bound.inferred.overrides.resilience or ResiliencePolicies()
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
    if inspect.iscoroutinefunction(fn):
        return fn

    wrapped_attr: Any = getattr(fn, "__wrapped__", None)
    if wrapped_attr is not None and inspect.iscoroutinefunction(wrapped_attr):
        return fn

    async def _wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    return _wrapper


def _to_jsonable(value: Any) -> Any:
    model_dump: Callable[..., Any] | None = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return value
