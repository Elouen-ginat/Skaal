"""Backend — a Skaal `App` that exposes business logic to other Skaal apps.

The backend declares its `Store[Task]` and `@app.function`s and lets Skaal
expose them at `/_skaal/invoke/<function_name>` automatically. A small
FastAPI surface is mounted on top for cases where a non-Skaal client (a
browser, a curl command) wants nicer URLs and a streaming endpoint.

Run on its own:

    pip install "skaal[serve,fastapi,examples]"
    skaal run examples.04_fullstack_split.backend:app --port 8000

Inspect the auto-exposed function endpoints:

    curl -s -X POST http://localhost:8000/_skaal/invoke/list_tasks \
        -H 'content-type: application/json' -d '{}'
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from skaal import App, RetryPolicy, Store

# ── Domain types ──────────────────────────────────────────────────────────────


class Task(BaseModel):
    id: str
    title: str
    done: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Skaal app ─────────────────────────────────────────────────────────────────

app = App("fullstack-backend")


@app.storage(read_latency="< 10ms", durability="persistent")
class Tasks(Store[Task]):
    """Persistent task store. Solver picks SQLite locally, DynamoDB on AWS."""


# ── Business logic — resilience policies live on the function ────────────────


@app.function(retry=RetryPolicy(max_attempts=2, base_delay_ms=10, max_delay_ms=20))
async def create_task(id: str, title: str) -> dict:
    if await Tasks.get(id) is not None:
        return {"error": f"Task {id!r} already exists"}
    task = Task(id=id, title=title)
    await Tasks.set(id, task)
    return task.model_dump()


@app.function()
async def complete_task(id: str) -> dict:
    task = await Tasks.get(id)
    if task is None:
        return {"error": f"Task {id!r} not found"}
    task.done = True
    await Tasks.set(id, task)
    return task.model_dump()


@app.function()
async def list_tasks() -> dict:
    items = [task.model_dump() for _, task in await Tasks.list()]
    return {"items": items, "count": len(items)}


@app.function()
async def delete_task(id: str) -> dict:
    await Tasks.delete(id)
    return {"ok": True, "deleted": id}


@app.function()
async def stream_progress(task_id: str) -> AsyncIterator[str]:
    """Async generator — yields one Server-Sent Event per simulated step."""
    for step in range(1, 6):
        await asyncio.sleep(0.4)
        yield f"data: step {step}/5 for {task_id}\n\n"
    yield "data: [done]\n\n"


# ── Optional FastAPI surface (REST + SSE) ────────────────────────────────────
#
# Skaal already exposes every `@app.function` at `/_skaal/invoke/<name>`, so
# any other Skaal app can call them via `AppRef` without this section. We
# mount a FastAPI router only for the streaming endpoint and for browser-
# friendly REST URLs.

api = FastAPI(title="Skaal x FastAPI backend")


def _raise_for_error(result: dict, *, not_found: bool = False, conflict: bool = False) -> dict:
    if "error" not in result:
        return result
    code = (
        status.HTTP_409_CONFLICT
        if conflict
        else status.HTTP_404_NOT_FOUND
        if not_found
        else status.HTTP_400_BAD_REQUEST
    )
    raise HTTPException(status_code=code, detail=result["error"])


@api.get("/tasks/{task_id}/progress")
async def http_stream_progress(task_id: str) -> StreamingResponse:
    """Streaming SSE endpoint — `AppRef` cannot consume this; httpx can."""
    return StreamingResponse(
        app.invoke_stream(stream_progress, task_id=task_id),
        media_type="text/event-stream",
    )


app.mount_asgi(api, attribute="api")
