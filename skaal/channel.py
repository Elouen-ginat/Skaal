"""`Channel[T, B]` — typed pub/sub primitive.

The `wire_local` / `wire_redis` plumbing has been removed; the new runtime
binds channels through the bound-plan pipeline (Phase 4 of ADR 028). The
optional second generic ``B`` is a `Backend` type-pin per ADR 032 §4.4 —
``class Events(Channel[OrderEvent, RedisChannel])`` pins this resource to
Redis Streams regardless of the active environment's defaults.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Generic

from typing_extensions import TypeVar

from skaal.backends._base import Backend

T = TypeVar("T")
B = TypeVar("B", bound=Backend, default=Backend)


class Channel(Generic[T, B]):
    """A typed, buffered channel for inter-component messaging.

    `Channel.send` and `Channel.receive` are placeholders until the runtime
    binds a concrete backend. The backend selection lives in the binding
    layer (Phase 3 of ADR 028); a declaration-site pin is the second
    generic parameter ``B`` (ADR 032 §4.4).
    """

    def __init__(self, buffer: int = 1000) -> None:
        self.buffer = buffer
        self._backend: Any | None = None
        self._backend_name: str | None = None
        self._wired: bool = False

    async def send(self, item: T) -> None:
        raise NotImplementedError(
            "Channel.send() has no backend wired yet. The runtime wires channels through the "
            "bound plan in Phase 4 of ADR 028."
        )

    async def receive(self) -> AsyncIterator[T]:
        raise NotImplementedError("Channel.receive() has no backend wired yet.")
        yield  # pragma: no cover

    async def native(self) -> Any:
        """Return the native SDK client for the wired channel backend.

        For type-pinned channels (``class Events(Channel[Order, RedisChannel])``),
        Pylance resolves the concrete SDK type via the backend token's
        ``NativeClient`` declaration in Phase 5b.

        Raises:
            NotImplementedError: If the channel has not been wired yet.
        """
        if self._backend is None:
            raise NotImplementedError(
                "Channel.native() has no backend wired yet. The runtime wires "
                "channels through the bound plan in Phase 4 of ADR 028."
            )
        backend_native = getattr(self._backend, "native", None)
        if callable(backend_native):
            result = backend_native()
            if hasattr(result, "__await__"):
                return await result
            return result
        return self._backend

    def __repr__(self) -> str:
        status = "wired" if self._wired else "unwired"
        return f"Channel(buffer={self.buffer}, backend={self._backend_name!r}, {status})"
