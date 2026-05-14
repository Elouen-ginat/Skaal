"""Adapter for `JOB` resources.

The Phase 4 cut wires an asyncio-queue worker per registered job: an
HTTP route at ``POST /_jobs/<name>/enqueue`` accepts a JSON payload and
posts it to the queue; a background task consumes the queue and calls
the user callable. Idempotency keys, dead-letter queues, and retry
budgets are deferred to the follow-up Phase 4 deploy work.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skaal.binding.model import BoundResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: BoundResource, target: Any) -> None:
    """Wire an in-process queue + worker task for the registered job."""
    if target is None:
        return
    if bound.backend != "asyncio":
        from skaal.errors import RuntimeAdapterMissing

        raise RuntimeAdapterMissing(f"job/{bound.backend}")

    bare = bound.inferred.id.split(":")[-1].split(".")[-1]
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    runtime.state.setdefault("job_queues", {})[bare] = queue
    worker_task: asyncio.Task[None] | None = None

    async def _worker() -> None:
        while True:
            payload = await queue.get()
            try:
                await target(**payload)
            except Exception:
                # Phase 4 ships a minimal contract; richer error
                # handling lands with the deploy-time DLQ work.
                pass
            finally:
                queue.task_done()

    async def _startup() -> None:
        nonlocal worker_task
        worker_task = asyncio.create_task(_worker(), name=f"skaal-job-{bare}")

    async def _shutdown() -> None:
        import contextlib

        if worker_task is not None:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await worker_task

    async def endpoint(request: Any) -> Any:
        from starlette.responses import JSONResponse

        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {"value": payload}
        await queue.put(payload)
        return JSONResponse({"enqueued": bare})

    runtime.add_route(f"/_jobs/{bare}/enqueue", endpoint, method="POST")
    runtime.add_startup_hook(_startup)
    runtime.add_shutdown_hook(_shutdown)
