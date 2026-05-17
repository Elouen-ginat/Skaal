"""Adapter for `JOB` resources.

The Phase 4 cut wires an asyncio-queue worker per registered job: an
HTTP route at ``POST /_jobs/<name>/enqueue`` accepts a JSON payload and
posts it to the queue; a background task consumes the queue and calls
the user callable. Idempotency keys, dead-letter queues, and retry
budgets are deferred to the follow-up Phase 4 deploy work.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any, cast

from starlette.requests import Request
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from skaal.binding.model import PlannedResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: PlannedResource, target: Any) -> None:
    """Wire an in-process queue + worker task for the registered job."""
    if target is None:
        return
    if bound.backend != "asyncio":
        from skaal.errors import RuntimeAdapterMissing

        raise RuntimeAdapterMissing(f"job/{bound.backend}")

    bare: str = bound.inferred.source.bare_name
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    runtime.state.job_queues[bare] = queue
    worker_task: asyncio.Task[None] | None = None

    async def _worker() -> None:
        while True:
            payload: dict[str, Any] = await queue.get()
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
        if worker_task is not None:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await worker_task

    async def endpoint(request: Request) -> JSONResponse:
        payload: Any
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {"value": payload}
        await queue.put(cast(dict[str, Any], payload))
        return JSONResponse({"enqueued": bare})

    runtime.add_route(f"/_jobs/{bare}/enqueue", endpoint, method="POST")
    runtime.add_startup_hook(_startup)
    runtime.add_shutdown_hook(_shutdown)
