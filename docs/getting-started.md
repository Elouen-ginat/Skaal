# Getting Started

This page gets you from zero to a running Skaal app with the smallest possible surface: one `Store`, one exposed function, and the local runtime.

## Install

Start with the local runtime:

```bash
pip install "skaal[serve]"
```

Add extras when you need them:

```bash
pip install "skaal[fastapi]"      # mounted FastAPI apps, uploads, streaming
pip install "skaal[deploy,aws]"   # build and deploy to AWS with Pulumi
```

## Write a small app

Create `counter_app.py`:

```python
from skaal import App, Store

app = App("counter")


@app.storage
class Counts(Store[int]):
    """Simple named counters."""


@app.expose()
async def increment(name: str, by: int = 1) -> dict:
    current = await Counts.get(name) or 0
    value = current + by
    await Counts.set(name, value)
    return {"name": name, "value": value}
```

## Run it

```bash
skaal run counter_app:app
```

What you see:

- A local ASGI server on `http://127.0.0.1:8000`.
- Generated invoke endpoints under `/_skaal/invoke/*`.
- In-memory local storage by default.

What gets written:

- Nothing yet. `skaal run` does not render deploy artifacts.

## Call the app

Increment a counter:

```bash
curl -s http://127.0.0.1:8000/_skaal/invoke/increment \
  -H "Content-Type: application/json" \
  -d '{"name": "hits", "by": 3}'
```

Read the current value back:

```bash
curl -s http://127.0.0.1:8000/_skaal/invoke/get_count \
    -H "Content-Type: application/json" \
    -d '{"name": "hits"}'
```

## Add environments when you need them

Local development works without `skaal.toml`. When you want named environments, add one at the repo root:

```toml
[env.local]
target = "local"

[env.prod]
target = "aws"
region = "us-east-1"
```

Then `skaal plan counter_app:app --env local` and `skaal deploy counter_app:app --env prod` can resolve the environment by name.

## If you want a full example instead

Run the repository counter app directly:

```bash
skaal run examples.counter:app
```

Or jump to [Examples](examples.md) if you prefer a mounted FastAPI API, uploads, or streaming.

## Project scaffold status

!!! note "`skaal init`"

    The project scaffolder is planned but not yet implemented in `0.4.0a0`. For now, start from a single file or copy one of the repository examples.

## Next

- Continue to [Concepts](concepts.md) if you want the vocabulary first.
- Continue to [Tutorials](tutorials/index.md) if you want the guided path.
- Continue to [CLI commands](cli.md) if you want the full command surface.
