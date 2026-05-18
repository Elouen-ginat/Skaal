<div id="top"></div>

# Skaal

[![CI](https://img.shields.io/github/actions/workflow/status/Elouen-ginat/Skaal/ci.yml?branch=main&label=CI)](https://github.com/Elouen-ginat/Skaal/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-2E8B57)](LICENSE)
[![Targets](https://img.shields.io/badge/targets-local%20%7C%20AWS%20%7C%20GCP-0F766E)](#what-skaal-targets)
[![Status](https://img.shields.io/badge/status-0.4.0--alpha-orange)](#status)

**Your Python app is your architecture.**

Write classes and functions. Skaal infers the infrastructure, generates the Pulumi program, and keeps the resource classes themselves as the typed clients. Pylance can follow a call from your app code down to the native SDK client without a code generation step.

## Quickstart

This is a runnable local app using the current `0.4.x` surface:

```python
from typing import Any

from skaal import App, Store

app = App("counter")


@app.storage
class Counts(Store[int]):
    """Named counters stored in Skaal's default KV backend."""


@app.expose()
async def increment(name: str, by: int = 1) -> dict[str, Any]:
    current = await Counts.get(name) or 0
    new_value = current + by
    await Counts.set(name, new_value)
    return {"name": name, "value": new_value}


@app.expose()
async def get_count(name: str) -> dict[str, Any]:
    return {"name": name, "value": await Counts.get(name) or 0}
```

Run it locally:

```bash
pip install "skaal[serve,runtime]"
skaal run app:app
```

Exercise the endpoints:

```bash
curl -s http://localhost:8000/increment -d '{"name": "hits"}'
curl -s http://localhost:8000/get_count -d '{"name": "hits"}'
```

## Working examples in this repo

- [`examples/counter.py`](examples/counter.py) — minimal `Store[T]` plus `@app.expose()` functions.
- [`examples/todo_api/app.py`](examples/todo_api/app.py) — FastAPI mounted on Skaal with `Store[T]` and relational `Table` storage.
- [`examples/blob_smoke.py`](examples/blob_smoke.py) — `BlobStore` declarations and blob listing/reads.
- [`examples/session_cache.py`](examples/session_cache.py) — backend pinning with `Store[T, Redis]` and TTL handling.
- [`examples/team_directory.py`](examples/team_directory.py) — native secondary-index queries with `SecondaryIndex`.

The CLI stays symmetrical across local and cloud targets:

```bash
skaal run examples.counter:app
skaal plan examples.todo_api:app --env prod
skaal deploy examples.todo_api:app --env prod
```

When you need backend-specific features, pin the second generic parameter and use the typed native client. This is the same pattern used in [`examples/session_cache.py`](examples/session_cache.py):

```python
from pydantic import BaseModel

from skaal import App, Store
from skaal.backends.tokens import Redis

app = App("session-cache")


class SessionRecord(BaseModel):
    id: str
    user_id: str


@app.storage
class Sessions(Store[SessionRecord, Redis]):
    default_ttl = "30m"


client = await Sessions.native()  # redis.asyncio.Redis
```

## How it works

1. **Declare** resources with `@app.storage` and functions with `@app.expose()`, `@app.schedule(...)`, or `@app.job(...)`.
2. **Infer** an environment-independent application plan by walking the `App` graph.
3. **Bind** that plan against an environment (`local`, `aws`, `gcp`) using Skaal's backend registry and defaults.
4. **Generate** Pulumi programs, Dockerfiles, and handler entrypoints from the bound result.
5. **Deploy** via Pulumi. The `skaal.lock` file pins each binding so the next plan is empty unless code changed.

For full HTTP routing, mount any ASGI app (FastAPI, Starlette, Litestar) — Skaal deploys it; the framework you already know owns the routes:

```python
from fastapi import FastAPI
api = FastAPI()
app.mount("/api", api)
```

## What Skaal targets

- **Local** — SQLite, filesystem, in-process topics, async functions, APScheduler.
- **AWS** — DynamoDB, S3, SQS, Lambda, EventBridge, RDS Postgres, Secrets Manager.
- **GCP** — Firestore, GCS, Pub/Sub, Cloud Run, Cloud Scheduler, Cloud SQL, Secret Manager.

The `0.4.0` cut ships AWS first; GCP follows in a `0.4.x` point release.

## Installation

```bash
pip install skaal                       # base
pip install "skaal[serve,runtime]"      # local development
pip install "skaal[deploy,aws,runtime]" # AWS
pip install "skaal[deploy,gcp,runtime]" # GCP
```

## Status

**Alpha (`0.4.0a0`).** The framework is functional end-to-end on the `local` target and against AWS via Pulumi. The current supported surface is the redesign-era API shown above: `App`, `Module`, `Store[T, B]`, `BlobStore[B]`, `Topic[T, B]`, `Table[B]`, `@app.storage`, `@app.expose()`, `@app.schedule(...)`, and `@app.job(...)`. See [`notes/redesign-status.md`](notes/redesign-status.md) for the live progress tracker against [ADR 028](notes/design/028-code-first-infra-redesign.md).

Roadmap and design decisions: [ADR index](notes/design/).

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
