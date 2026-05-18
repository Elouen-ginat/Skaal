# HTTP integration

Skaal does not try to be a web framework. `@app.expose()` defines application work and the runtime boundary around that work. Your mounted ASGI app still owns the public routes, validation, auth, middleware, and OpenAPI surface.

Use FastAPI, Starlette, or another ASGI app via `app.mount("/", api)` and call Skaal compute through `app.invoke(...)` or `app.invoke_stream(...)`.

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from skaal import App, Retry

app = App("api")
api = FastAPI()


@app.expose(retry=Retry(max_attempts=3))
async def predict(features: dict) -> dict:
    return {"ok": True, "features": features}


@app.expose()
async def stream_tokens(prompt: str):
    for token in prompt.split():
        yield f"data: {token}\n\n"


@api.get("/items/{item_id}")
async def get_item(item_id: str) -> dict:
    return await app.invoke(predict, features={"id": item_id})


@api.get("/chat")
async def chat(prompt: str) -> StreamingResponse:
    return StreamingResponse(
        app.invoke_stream(stream_tokens, prompt=prompt),
        media_type="text/event-stream",
    )


app.mount("/", api)
```

## Route ownership

- Your mounted ASGI app owns every public path you mount.
- Skaal reserves `/_skaal/*` for runtime endpoints such as `POST /_skaal/invoke/<function>`.
- Public handlers should call `app.invoke(...)` at the boundary where you want Skaal runtime policies to apply.

## Why `app.invoke(...)` matters

- Use `await app.invoke(...)` from your FastAPI or Starlette handlers when you want Skaal retry, circuit-breaker, rate-limit, or bulkhead policies to apply.
- Use `app.invoke_stream(...)` for async-generator functions and hand the returned async iterator to `StreamingResponse`.
- Calling the decorated function directly, like `await predict(...)`, is still allowed for local code paths but bypasses the resilience middleware.

## Common failures

### Route collisions

If your ASGI app serves under `/_skaal/*`, you are overlapping Skaal's reserved runtime namespace. Move the route or mount your app somewhere else.

### Calling the function directly by accident

If a FastAPI route does `await predict(...)` instead of `await app.invoke(predict, ...)`, the code still runs but runtime policies do not. That is fine for internal helpers and wrong for the public boundary.

### Streaming the generator itself

If a route returns `stream_tokens(prompt)` instead of `app.invoke_stream(stream_tokens, prompt=prompt)`, the response bypasses Skaal's runtime boundary. Hand `invoke_stream(...)` directly to `StreamingResponse`.

## Good example anchors

- `examples.todo_api:app` mounts FastAPI over Skaal compute for a CRUD API.
- `examples.fastapi_streaming:app` streams SSE from a Skaal async generator.

## Next

- Read [Tutorial 2](tutorials/http-api.md) for the step-by-step version.
- Read [Examples](examples.md) for full repo apps.
