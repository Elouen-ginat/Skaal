# Tutorial 5: Files and Streaming

The earlier tutorials cover the core app and environment flow. This last tutorial adds two practical I/O patterns that already exist in the repository examples: blob storage and streaming responses.

## What You Will Learn

- how to declare a `BlobStore`
- how to upload and list files through a mounted FastAPI app
- how to stream data from an async Skaal function with `app.invoke_stream(...)`

## Install the HTTP Extras

```bash
pip install "skaal[serve,fastapi]"
```

## Store Files With `BlobStore`

Create a mounted FastAPI app with a blob surface:

```python
from fastapi import FastAPI, File, UploadFile

from skaal import App, BlobStore

app = App("file-api")
api = FastAPI(title="Tutorial File API")


@app.storage(kind="blob")
class Uploads(BlobStore):
    pass


@api.post("/files")
async def upload_file(file: UploadFile = File(...)) -> dict:
    key = f"uploads/{file.filename or 'upload.bin'}"
    created = await Uploads.put_bytes(
        key,
        await file.read(),
        content_type=file.content_type,
    )
    return {"key": created.key, "size": created.size}


@api.get("/files")
async def list_files() -> dict:
    page = await Uploads.list_page(prefix="uploads/", limit=20)
    return {
        "items": [item.key for item in page.items],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
    }


app.mount("/", api)
```

Run it:

```bash
skaal run file_api:app --env local
```

Upload a file:

```bash
curl -s -X POST http://127.0.0.1:8000/files \
  -F "file=@README.md"
```

List the upload prefix:

```bash
curl -s http://127.0.0.1:8000/files
```

The full repository example at `examples/file_upload_api/app.py` expands this into downloads, metadata, and cursor validation.

## Stream a Response

Streaming uses a different part of the runtime: `app.invoke_stream(...)`.
Add this code to the same app:

```python
import asyncio

from fastapi.responses import StreamingResponse

from skaal import Retry


@app.expose(retry=Retry(max_attempts=2, base_delay_ms=10, max_delay_ms=25))
async def stream_tokens(prompt: str):
    for token in prompt.split():
        await asyncio.sleep(0.02)
        yield f"data: {token}\n\n"
    yield "data: [done]\n\n"


@api.get("/chat")
async def chat(prompt: str) -> StreamingResponse:
    return StreamingResponse(
        app.invoke_stream(stream_tokens, prompt=prompt),
        media_type="text/event-stream",
    )
```

Call it with a client that keeps the connection open:

```bash
curl -N "http://127.0.0.1:8000/chat?prompt=hello%20streaming%20world"
```

This is the pattern used in `examples/fastapi_streaming/app.py`.

## What this does not cover

- backend-specific blob options in `skaal.toml`
- auth or validation around uploads
- cloud deploy configuration for the mounted app

## Where To Go Next

- Read [Python API: Data Surfaces](../reference/python-api-data.md) for `BlobStore` and the typed data APIs.
- Read [Python API: Types and Policies](../reference/python-api-types.md) for `Retry` and related resilience objects.
- Revisit [Examples](../examples.md) to inspect the full repository apps.
- Read [HTTP Integration](../http.md) for the mounted ASGI model.
- Read [CLI](../cli.md) for the operational command loop behind the tutorials.

You now have the full progressive path: local storage, mounted HTTP, planning, migrations, and advanced I/O.
