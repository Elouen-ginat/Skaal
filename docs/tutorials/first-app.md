# Tutorial 1: Your first app

This tutorial keeps the surface intentionally small: one store, one exposed function, and the local runtime. The goal is to make the app model feel concrete before you add public HTTP or deployment concerns.

## What You Will Learn

- how `App` groups your application model
- how `@app.storage` declares a typed resource
- how `@app.expose()` becomes a callable runtime surface
- how `skaal run` exposes those functions locally

## Build the Counter App

Create `counter_app.py` with one typed store and a few functions:

```python
from skaal import App, Store

app = App("counter")


@app.storage
class Counts(Store[int]):
  """Named integer counters."""


@app.expose()
async def increment(name: str, by: int = 1) -> dict:
    current = await Counts.get(name) or 0
    new_value = current + by
    await Counts.set(name, new_value)
    return {"name": name, "value": new_value}


@app.expose()
async def get_count(name: str) -> dict:
    value = await Counts.get(name) or 0
    return {"name": name, "value": value}
```

This is the smallest useful Skaal shape:

- `App("counter")` defines the application boundary.
- `Counts` is a storage surface that Skaal can infer and bind by environment.
- the functions describe work the runtime can execute.

## Run the App

Install the local server support and start the app:

```bash
pip install "skaal[serve]"
skaal run counter_app:app --env local
```

If `skaal.toml` does not exist yet, Skaal still gives you a baseline `local` environment.

## Call the Generated Endpoints

When you do not mount your own ASGI app, Skaal exposes the compute functions directly as local HTTP endpoints.

Increment a counter:

```bash
curl -s http://127.0.0.1:8000/_skaal/invoke/increment \
  -H "Content-Type: application/json" \
  -d '{"name": "hits"}'
```

Read it back:

```bash
curl -s http://127.0.0.1:8000/_skaal/invoke/get_count \
  -H "Content-Type: application/json" \
  -d '{"name": "hits"}'
```

## What Skaal Did for You

- The `Counts` type stayed vendor-neutral.
- The runtime turned each function into a local endpoint.
- The same declaration can later bind against a named environment without changing the function bodies.

If you want to compare this stripped-down version with the repository example, read `examples/counter.py`.

## What this does not cover

- mounted FastAPI or Starlette routes
- deploy artifacts or `skaal.lock`
- relational, blob, or topic primitives

## Reference Links

- Read [Python API: Core and Decorators](../reference/python-api-core.md) for `App` and the decorator surface.
- Read [Python API: Data Surfaces](../reference/python-api-data.md) for `Store` and the typed storage APIs.
- Read [Configuring your environments](../cli-configuration.md) when you want to add `skaal.toml`.

## Continue

Next: [Tutorial 2: Adding HTTP routes](http-api.md).
