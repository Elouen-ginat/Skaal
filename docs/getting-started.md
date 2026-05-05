# Getting Started

Skaal is best when treated as an application planner, not a collection of backend helpers. You define the app once, add constraints to the surfaces that matter, and let the planner determine a target-specific implementation.

## Install

For local development:

```bash
pip install "skaal[serve]"
```

If you need schedules, auth, background jobs, or telemetry support:

```bash
pip install "skaal[serve,runtime]"
```

## Smallest Useful Example

```python
from skaal import App, storage
from skaal.storage import Map

app = App("hello")


@storage(read_latency="< 10ms", durability="ephemeral")
class Counters(Map[str, int]):
    pass
```

## Plan, Build, Deploy

```bash
skaal plan --app myapp:app --catalog catalogs/local.toml
skaal build --app myapp:app --target local --catalog catalogs/local.toml
skaal deploy --app myapp:app --target local --catalog catalogs/local.toml
```

Local deployment produces generated artifacts under `artifacts/`, including a `Dockerfile`, `main.py`, Pulumi configuration, and stack metadata.

## Where To Go Next

- [CLI guide](cli.md) for the full command surface.
- [HTTP integration](http.md) for FastAPI, Starlette, and Dash patterns.
- [Python API reference](reference/python-api.md) for in-process planning and deployment.
