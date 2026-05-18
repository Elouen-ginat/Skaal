<div id="top"></div>

# Skaal

[![CI](https://img.shields.io/github/actions/workflow/status/Elouen-ginat/Skaal/ci.yml?branch=main&label=CI)](https://github.com/Elouen-ginat/Skaal/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-2E8B57)](LICENSE)
[![Targets](https://img.shields.io/badge/targets-local%20%7C%20AWS%20%7C%20GCP-0F766E)](#what-skaal-targets)
[![Status](https://img.shields.io/badge/status-0.4.0--alpha-orange)](#status)

**Your Python app is your architecture.**

Write classes and functions. Skaal infers the infrastructure, generates the Pulumi, and your primitive classes are the typed clients. Pylance follows every call site straight down to the underlying SDK. One codebase. One mental model. `skaal deploy` knows what to build.

## What Skaal looks like

```python
from skaal import App, BlobStore, Cron, Store, Topic
from pydantic import BaseModel

class User(BaseModel):
    id: str
    email: str

class Users(Store[User]):
    """One table. The class is the table."""
    by_email = "email"  # declarative secondary index

class Avatars(BlobStore):
    """One bucket. The class is the bucket."""

class SignupEvents(Topic[User]):
    """One topic. The class is the topic."""

app = App("acme")

@app.expose
async def signup(user: User) -> User:
    await Users.put(user.id, user)
    await SignupEvents.publish(user)
    return user

@app.schedule(Cron("0 * * * *"))
async def hourly_compact() -> None:
    ...
```

The class **is** the typed client, importable from anywhere with no codegen step:

```python
from acme.users import Users
user: User | None = await Users.get("u1")   # Pylance: user is User | None
```

When you need a backend-specific feature, you pin the type and get the real SDK client back, typed:

```python
from skaal import Store
from skaal.backends.redis import Redis

class Sessions(Store[SessionRecord, Redis]):
    """Session rows backed by Redis in every environment."""

r = await Sessions.native()    # redis.asyncio.Redis, in every environment
```

The CLI is symmetric:

```bash
skaal run                      # local: SQLite + filesystem + in-memory topic
skaal plan --env prod          # diff: Users -> DynamoDB, Avatars -> S3, ...
skaal deploy --env prod        # Pulumi up against AWS
```

There is no constraint DSL. There is no catalog you maintain. There is no solver. The shape of the code is the deployment plan; an environment picks the backend by a fixed table the framework owns.

## How it works

1. **Declare** classes (`Store[T]`, `BlobStore`, `Topic[T]`, `Table`) and functions (`@app.expose`, `@app.schedule`, `@app.job`).
2. **Infer** an environment-independent `Blueprint` by walking the `App` graph.
3. **Bind** the blueprint against an environment (`local`, `aws`, `gcp`) using a fixed defaults table.
4. **Generate** Pulumi programs, Dockerfiles, and handler entrypoints from the bound plan.
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

**Alpha (`0.4.0a0`).** The framework is functional end-to-end on the `local` target and against AWS via Pulumi. The public surface (`App`, `Module`, `Store[T, B]`, `BlobStore[B]`, `Topic[T, B]`, `Table[B]`, `@app.expose`, `@app.schedule`, `@app.job`) is the supported surface going forward — see [`notes/redesign-status.md`](notes/redesign-status.md) for the live progress tracker against [ADR 028](notes/design/028-code-first-infra-redesign.md).

Roadmap and design decisions: [ADR index](notes/design/).

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
