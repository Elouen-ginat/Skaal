from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol, TypeAlias, TypeVar

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)


class InvokeContext(Protocol):
    """Read-only metadata for a single invocation attempt."""

    function_name: str
    kwargs: dict[str, Any]
    is_stream: bool
    attempt: int


BeforeInvoke: TypeAlias = Callable[[InvokeContext], Awaitable[None]]


class StreamFn(Protocol[T_co]):
    """Typing helper for ``@app.function`` async generators."""

    def __call__(self, **kwargs: Any) -> AsyncIterator[T_co]: ...
