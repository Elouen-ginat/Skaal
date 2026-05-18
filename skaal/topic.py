"""`Topic[T, B]` — typed pub/sub primitive.

The `wire_local` / `wire_redis` plumbing has been removed; the new runtime
binds channels through the bound-plan pipeline (Phase 4 of ADR 028). The
optional second generic ``B`` is a `Backend` type-pin per ADR 032 §4.4 —
``class Events(Topic[OrderEvent, RedisChannel])`` pins this resource to
Redis Streams regardless of the active environment's defaults.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any, Generic, cast, overload

from typing_extensions import TypeVar

from skaal.backends._base import Backend

if TYPE_CHECKING:
    from skaal.backends._native_types import RedisNativeClient, SqsClientProtocol
    from skaal.backends.tokens.messaging import RedisChannel, Sqs

T = TypeVar("T")
B = TypeVar("B", bound="Backend[Any]", default="Backend[Any]")


class Topic(Generic[T, B]):
    """A typed, buffered channel for inter-component messaging.

    `Topic.send` and `Topic.receive` are placeholders until the runtime
    binds a concrete backend. The backend selection lives in the binding
    layer (Phase 3 of ADR 028); a declaration-site pin is the second
    generic parameter ``B`` (ADR 032 §4.4).
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls is Topic:
            return
        from skaal.decorators import _attach_channel_inferred

        _attach_channel_inferred(cls)

    def __init__(self, buffer: int = 1000) -> None:
        self.buffer = buffer
        self._backend: Any | None = None
        self._backend_name: str | None = None
        self._wired: bool = False

    def wire(self, backend: Any, *, backend_name: str | None = None) -> None:
        """Bind a concrete channel backend to this topic instance."""
        self._backend = backend
        self._backend_name = backend_name or getattr(backend, "name", backend.__class__.__name__)
        self._wired = True

    async def send(self, item: T) -> None:
        if self._backend is None:
            raise NotImplementedError(
                "Topic.send() has no backend wired yet. The runtime wires channels through the "
                "bound plan in Phase 4 of ADR 028."
            )

        send = cast(Callable[[T], Awaitable[None]] | None, getattr(self._backend, "send", None))
        if send is not None:
            await send(item)
            return

        publish = cast(
            Callable[[str, T], Awaitable[None]] | None,
            getattr(self._backend, "publish", None),
        )
        if publish is not None:
            await publish(self._topic_name(), item)
            return

        raise NotImplementedError(
            f"Topic backend {self._backend_name!r} does not expose send()/publish()."
        )

    async def receive(self) -> AsyncIterator[T]:
        if self._backend is None:
            raise NotImplementedError("Topic.receive() has no backend wired yet.")

        receive = cast(
            Callable[[], AsyncIterator[T]] | None,
            getattr(self._backend, "receive", None),
        )
        if receive is not None:
            async for item in receive():
                yield item
            return

        subscribe = cast(
            Callable[[str], AsyncIterator[T]] | None,
            getattr(self._backend, "subscribe", None),
        )
        if subscribe is not None:
            async for item in subscribe(self._topic_name()):
                yield item
            return

        raise NotImplementedError(
            f"Topic backend {self._backend_name!r} does not expose receive()/subscribe()."
        )

    @overload
    async def native(self: Topic[T, RedisChannel]) -> RedisNativeClient: ...

    @overload
    async def native(self: Topic[T, Sqs]) -> SqsClientProtocol: ...

    async def native(self) -> Any:
        """Return the native SDK client for the wired channel backend.

        For type-pinned topics (``class Events(Topic[Order, RedisChannel])``),
        Pylance resolves the concrete SDK type via the backend token's
        ``NativeClient`` declaration in Phase 5b.

        Raises:
            NotImplementedError: If the channel has not been wired yet.
        """
        from skaal._native import resolve_native

        if self._backend is None:
            raise NotImplementedError(
                "Topic.native() has no backend wired yet. The runtime wires "
                "channels through the bound plan in Phase 4 of ADR 028."
            )
        return await resolve_native(self._backend)

    def __repr__(self) -> str:
        status = "wired" if self._wired else "unwired"
        return f"Topic(buffer={self.buffer}, backend={self._backend_name!r}, {status})"

    def _topic_name(self) -> str:
        return self.__class__.__name__
