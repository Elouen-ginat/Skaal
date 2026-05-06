"""Outbox engine — transactional event relay.

User code writes into the outbox via :meth:`Outbox.write`; the engine drains
pending rows and ships them to the configured channel.  The storage write and
outbox-row write happen inside a single :meth:`atomic_update` so success and
publish intent are coupled.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol, TypeGuard, cast

from typing_extensions import TypedDict

from skaal.patterns import Outbox
from skaal.runtime.engines.base import BackgroundTaskEngine
from skaal.types import AsyncPublishTarget

if TYPE_CHECKING:
    from skaal.backends.base import StorageBackend


class OutboxRow(TypedDict):
    payload: object
    written_at: str
    delivered: bool


class _WritableOutbox(Protocol):
    write: Callable[[str, object], Awaitable[None]]


class OutboxEngine(BackgroundTaskEngine):
    """Background relay that publishes pending outbox rows to a channel."""

    def __init__(self, outbox: Outbox[object], poll_interval: float = 0.05) -> None:
        super().__init__()
        self.outbox = outbox
        self.poll_interval = poll_interval
        self._queue_depth = 0

    async def start(self, context: Any) -> None:
        # Install a send helper on the outbox so user code has a one-liner:
        #     await orders_outbox.write(key, payload)
        writable_outbox = cast(_WritableOutbox, self.outbox)
        if not hasattr(writable_outbox, "write"):
            writable_outbox.write = self._write_factory()
        await self._start_background(self._relay_loop, name=f"outbox:{self._outbox_name()}")

    # ── Writer + relay ───────────────────────────────────────────────────────

    def _write_factory(self) -> Callable[[str, object], Awaitable[None]]:
        store_backend = _backend_of(self.outbox.storage)

        async def write(row_key: str, payload: object) -> None:
            """Atomically append *payload* to the outbox.

            The payload is stored under ``outbox:<row_key>:<ts>`` so ordering
            is preserved by the backend's lexicographic scan.
            """
            ts = f"{time.time_ns():020d}"
            key = f"outbox:{row_key}:{ts}"

            def _write(current: object) -> OutboxRow:
                return {"payload": payload, "written_at": ts, "delivered": False}

            await store_backend.atomic_update(key, _write)

        return write

    async def _relay_loop(self) -> None:
        store_backend = _backend_of(self.outbox.storage)
        channel = self.outbox.channel
        try:
            while not self._stopping.is_set():
                try:
                    pending = await store_backend.scan("outbox:")
                except Exception:
                    self._failures += 1
                    pending = []
                self._queue_depth = sum(
                    1 for _, row in pending if isinstance(row, dict) and not row.get("delivered")
                )
                delivered_any = False
                for key, row in sorted(pending):
                    if not isinstance(row, dict) or row.get("delivered"):
                        continue
                    try:
                        if not _is_async_publish_target(channel):
                            continue
                        await _publish_outbox_row(channel, row["payload"])
                    except Exception:
                        # Retry on next tick — at-least-once delivery.
                        self._failures += 1
                        continue

                    # Mark delivered.  For at-least-once the safest thing is to
                    # delete the row; for exactly-once we keep it marked so a
                    # downstream dedupe layer can reconcile.
                    try:
                        if self.outbox.delivery == "at-least-once":
                            await store_backend.delete(key)
                        else:
                            row["delivered"] = True
                            await store_backend.set(key, row)
                    except Exception:
                        self._failures += 1
                        continue
                    delivered_any = True
                if not delivered_any:
                    try:
                        await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_interval)
                    except TimeoutError:
                        continue
        except asyncio.CancelledError:
            return

    def snapshot_telemetry(self) -> dict[str, int | bool]:
        return {**super().snapshot_telemetry(), "queue_depth": self._queue_depth}

    def _outbox_name(self) -> str:
        return getattr(self.outbox.storage, "__name__", "outbox")


def _is_async_publish_target(value: object) -> TypeGuard[AsyncPublishTarget[object]]:
    if isinstance(value, type):
        return False
    send = getattr(value, "send", None)
    append = getattr(value, "append", None)
    return callable(send) or callable(append)


async def _publish_outbox_row(target: AsyncPublishTarget[object], payload: object) -> None:
    send = cast(Callable[[object], Awaitable[None]] | None, getattr(target, "send", None))
    if callable(send):
        await send(payload)
        return

    append = cast(Callable[[object], Awaitable[object]] | None, getattr(target, "append", None))
    if callable(append):
        await append(payload)
        return

    raise TypeError("Outbox channel must provide send() or append()")


def _backend_of(storage_cls: type[object]) -> StorageBackend:
    """Return the wired backend on a ``@storage`` class.

    ``Store`` classes keep their backend on a class-level
    attribute after ``cls.wire(backend)`` is called.
    """
    for attr in ("_backend", "__skaal_backend__"):
        backend = getattr(storage_cls, attr, None)
        if backend is not None:
            return cast("StorageBackend", backend)
    raise RuntimeError(
        f"outbox storage {storage_cls!r} has no wired backend — "
        "call cls.wire(backend) before starting the outbox engine"
    )
