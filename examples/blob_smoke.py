"""Blob smoke app for deploy-time AWS validation."""

from __future__ import annotations

from typing import Any

from skaal import App, BlobStore

app = App("blob-smoke")


@app.storage(kind="blob")
class Uploads(BlobStore):
    pass


@app.expose()
async def put_and_read(name: str, content: str) -> dict[str, Any]:
    key = f"uploads/{name}.txt"
    created = await Uploads.put_bytes(
        key,
        content.encode("utf-8"),
        content_type="text/plain",
        metadata={"source": "blob-smoke"},
    )
    stored = await Uploads.get_bytes(key)
    return {
        "key": created.key,
        "content": stored.decode("utf-8"),
        "size": created.size,
        "content_type": created.content_type,
    }


@app.expose()
async def list_uploads(prefix: str = "uploads/") -> dict[str, Any]:
    page = await Uploads.list_page(prefix=prefix, limit=20)
    return {
        "items": [item.key for item in page.items],
        "has_more": page.has_more,
        "next_cursor": page.next_cursor,
    }
