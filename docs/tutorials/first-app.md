# Tutorial 1: Build a Counter App

This tutorial keeps the surface intentionally small: one store, a few compute functions, and the local Skaal run loop. The goal is to make the application model feel concrete before you add a public HTTP framework or deployment target.

## What You Will Learn

- how `App` groups your application model
- how `@app.storage(...)` declares backend needs without choosing a backend directly
- how `@app.function()` becomes a callable runtime surface
- how `skaal run` exposes those functions locally

## Build the Counter App

Create `counter_app.py` with one typed store and a few functions:

```python
from skaal import App, Store

app = App("counter")


@app.storage(read_latency="< 5ms", durability="ephemeral")
class Counts(Store[int]):
    pass


@app.function()
async def increment(name: str, by: int = 1) -> dict:
    current = await Counts.get(name) or 0
    new_value = current + by
    await Counts.set(name, new_value)
    return {"name": name, "value": new_value}


@app.function()
async def get_count(name: str) -> dict:
    value = await Counts.get(name) or 0
    return {"name": name, "value": value}


@app.function()
async def list_counts() -> dict:
    entries = await Counts.list()
    return {"counts": dict(entries)}
```

This is the smallest useful Skaal shape:

- `App("counter")` defines the application boundary.
- `Counts` is a storage surface with requirements attached to it.
- the functions describe work the runtime can execute.

## Run the App

Install the local server support and start the app:

```bash
pip install "skaal[serve]"
skaal run counter_app:app
```

If you created a scaffolded project with `skaal init`, you can omit `counter_app:app` once `[tool.skaal] app` is set in `pyproject.toml`.

By default, Skaal uses the in-memory local backend for this storage surface. That keeps the feedback loop fast.

## Call the Generated Endpoints

When you do not mount your own ASGI app, Skaal exposes the compute functions directly as local HTTP endpoints.

Increment a counter:

```bash
curl -s http://127.0.0.1:8000/increment \
  -H "Content-Type: application/json" \
  -d '{"name": "hits"}'
```

Read it back:

```bash
curl -s http://127.0.0.1:8000/get_count \
  -H "Content-Type: application/json" \
  -d '{"name": "hits"}'
```

List every counter:

```bash
curl -s http://127.0.0.1:8000/list_counts \
  -H "Content-Type: application/json" \
  -d '{}'
```

## Make It Persistent

The same app can run against SQLite-backed local persistence without changing the code:

```bash
skaal run counter_app:app --persist
```

You can also choose the SQLite file explicitly:

```bash
skaal run counter_app:app --persist --db counter.db
```

That is the first important Skaal trade: you describe the behavior the store needs, then let the runtime decide which backend to use for the current environment.

## What Skaal Did for You

- The `Counts` type stayed vendor-neutral.
- The runtime turned each function into a local endpoint.
- The storage backend stayed swappable because the constraints live on the surface, not inside the function bodies.

If you want to compare this stripped-down version with the repository example, read `examples/counter.py`.

## Reference Links

- Read [Python API: Core and Decorators](../reference/python-api-core.md) for `App` and the decorator surface.
- Read [Python API: Data Surfaces](../reference/python-api-data.md) for `Store` and the typed storage APIs.
- Read [CLI Configuration](../cli-configuration.md) when you want `skaal run` defaults to come from `pyproject.toml` or `.skaal.env`.

## Continue

Next: [Tutorial 2: Add a FastAPI Surface](http-api.md).
