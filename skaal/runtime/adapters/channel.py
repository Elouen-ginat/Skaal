"""Adapter for `CHANNEL` resources.

The local-defaults entry for channels is `in-process` — a thin
asyncio-queue wrapper that ships with `skaal.topic`. The adapter is
a no-op for that case because the `Channel` subclass already self-wires
on instantiation; richer backends (Redis Streams, SQS, Pub/Sub) live
on the deploy side and raise `RuntimeAdapterMissing` here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skaal.binding.model import PlannedResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: PlannedResource, target: Any) -> None:
    """Verify the channel backend is supported locally; otherwise raise."""
    if bound.external:
        return
    if bound.backend in {"in-process"}:
        return

    from skaal.errors import RuntimeAdapterMissing

    raise RuntimeAdapterMissing(f"channel/{bound.backend}")
