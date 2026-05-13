"""`Channel[T]` — typed pub/sub primitive.

The `wire_local` / `wire_redis` plumbing has been removed; the new runtime
binds channels through the bound-plan pipeline (Phase 4 of ADR 028).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Generic, TypeVar

T = TypeVar("T")


class Channel(Generic[T]):
    """A typed, buffered channel for inter-component messaging.

    `Channel.send` and `Channel.receive` are placeholders until the runtime
    binds a concrete backend. The backend selection lives in the binding
    layer (Phase 3 of ADR 028).
    """

    def __init__(self, buffer: int = 1000) -> None:
        self.buffer = buffer
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

    def __repr__(self) -> str:
        status = "wired" if self._wired else "unwired"
        return f"Channel(buffer={self.buffer}, backend={self._backend_name!r}, {status})"
