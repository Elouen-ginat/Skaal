"""Projection engine — tails an EventLog and applies a handler per event.

The handler is a named function registered with the app/module; it receives
``(target, event)`` and is expected to update the target storage.  Progress
is checkpointed in the EventLog's backend under a dedicated key so restarts
resume cleanly.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, TypeGuard, cast

from skaal.patterns import Projection
from skaal.runtime.engines.base import BackgroundTaskEngine
from skaal.types import ProjectionDeadLetterSink, ProjectionFailurePayload, ProjectionHandler


class ProjectionEngine(BackgroundTaskEngine):
    """Background worker for a single :class:`skaal.patterns.Projection`."""

    def __init__(self, projection: Projection[object, object]) -> None:
        super().__init__()
        self.projection = projection

    async def start(self, context: Any) -> None:
        handler_name = self.projection.handler
        functions = cast(
            Mapping[str, ProjectionHandler[object, object]],
            getattr(context, "functions", {}) or {},
        )
        handler = functions.get(handler_name)
        if handler is None:
            # Defer failure — the solver validates this at plan time, but
            # tests may spin up an engine without a handler registered.
            handler = _missing_handler(handler_name)

        await self._start_background(
            lambda: self._run(handler),
            name=f"projection:{self.projection.handler}",
        )

    async def _run(self, handler: ProjectionHandler[object, object]) -> None:
        group = f"projection:{self.projection.handler}"
        target = self.projection.target
        strict = bool(getattr(self.projection, "strict", False))
        dead_letter = getattr(self.projection, "dead_letter", None)
        counter = 0
        try:
            async for offset, event in self.projection.source.subscribe(group):
                if self._stopping.is_set():
                    return
                try:
                    if inspect.iscoroutinefunction(handler):
                        await handler(target, event)
                    else:
                        handler(target, event)
                except Exception as exc:
                    self._failures += 1
                    if _is_projection_dead_letter_sink(dead_letter):
                        await _publish_dead_letter(
                            dead_letter,
                            payload=_build_projection_failure_payload(
                                handler_name=self.projection.handler,
                                offset=offset,
                                event=event,
                                exc=exc,
                            ),
                        )
                    if strict:
                        raise
                    continue
                counter += 1
                if counter % max(1, self.projection.checkpoint_every) == 0:
                    # subscribe() already writes consumer offset; this hook is
                    # reserved for snapshotting derived state in future versions.
                    pass
        except asyncio.CancelledError:
            return


def _missing_handler(name: str) -> ProjectionHandler[object, object]:
    async def _raise(*_a: object, **_kw: object) -> None:
        raise RuntimeError(f"projection handler {name!r} is not registered with the runtime")

    return _raise


def _build_projection_failure_payload(
    *,
    handler_name: str,
    offset: int,
    event: object,
    exc: BaseException,
) -> ProjectionFailurePayload:
    return {
        "pattern": "projection",
        "handler": handler_name,
        "offset": offset,
        "event": event,
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
        },
    }


def _is_projection_dead_letter_sink(value: object) -> TypeGuard[ProjectionDeadLetterSink]:
    if isinstance(value, type):
        return False
    send = getattr(value, "send", None)
    append = getattr(value, "append", None)
    return callable(send) or callable(append)


async def _publish_dead_letter(
    destination: ProjectionDeadLetterSink,
    *,
    payload: ProjectionFailurePayload,
) -> None:
    send = cast(
        Callable[[ProjectionFailurePayload], Awaitable[None]] | None,
        getattr(destination, "send", None),
    )
    if callable(send):
        await send(payload)
        return

    append = cast(
        Callable[[ProjectionFailurePayload], Awaitable[object]] | None,
        getattr(destination, "append", None),
    )
    if callable(append):
        await append(payload)
        return

    raise TypeError("Projection dead_letter target must provide send() or append()")
