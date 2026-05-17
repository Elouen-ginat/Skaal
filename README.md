<div id="top"></div>

# Skaal

[![CI](https://img.shields.io/github/actions/workflow/status/Elouen-ginat/Skaal/ci.yml?branch=main&label=CI)](https://github.com/Elouen-ginat/Skaal/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-2E8B57)](LICENSE)
[![Targets](https://img.shields.io/badge/targets-local%20%7C%20AWS%20%7C%20GCP-0F766E)](#what-skaal-targets)
[![Status](https://img.shields.io/badge/status-alpha%20redesign-orange)](#status)

**Your Python app is your architecture.**

Write classes and functions. Skaal infers the infrastructure, generates the Pulumi, and your primitive classes are the typed clients. Pylance follows every call site straight down to the underlying SDK. One codebase. One mental model. `skaal deploy` knows what to build.

## Status

> **Skaal is in the middle of a redesign from "Infrastructure as Constraints" to "code-first infrastructure" (`v0.3.x` → `v0.4.0`).**
>
> The new product is described in [ADR 028](notes/design/028-code-first-infra-redesign.md). The execution plan and live progress live in [ADR 029](notes/design/029-redesign-foundation-implementation-plan.md) and [`notes/redesign-status.md`](notes/redesign-status.md). Pre-redesign documentation pages still describe the constraint-solver model and will be replaced as Phase 7 lands.
>
> If you need a stable install today, pin `skaal==0.3.1`. New work happens on the `claude/plan-redesign-strategy-A5ixu` branch (the de-facto `v0.4.0-alpha` working branch), not on `main`.

## What Skaal will be

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
from skaal.backends.bigquery import BigQuery

class Sales(Table[BigQuery], partition_by="occurred_at"):
    transaction_id: str = Field(primary_key=True)

bq = await Sales.native()      # google.cloud.bigquery.Client, in every environment
```

The CLI is symmetric:

```bash
skaal run                      # local: SQLite + filesystem + in-memory topic
skaal plan --env prod          # diff: Users -> DynamoDB, Avatars -> S3, ...
skaal deploy --env prod        # Pulumi up against AWS
```

There is no constraint DSL. There is no catalog you maintain. There is no solver. The shape of the code is the deployment plan; an environment picks the backend by a fixed table the framework owns.

## How it works

1. **Declare** classes (`Store[T]`, `BlobStore`, `Topic[T]`, `Table[B]`) and functions (`@app.expose`, `@app.schedule`, `@app.job`).
2. **Infer** an environment-independent `Blueprint` by walking the `App` graph (Phase 2 of the redesign).
3. **Bind** the plan against an environment (`local`, `aws`, `gcp`) using a fixed defaults table (Phase 3).
4. **Generate** Pulumi programs, Dockerfiles, and handler entrypoints from the bound plan (Phase 4).
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
pip install skaal                       # base (currently the 0.3.x constraint product)
pip install "skaal[serve,runtime]"      # local development
pip install "skaal[deploy,aws,runtime]" # AWS
pip install "skaal[deploy,gcp,runtime]" # GCP
```

The `0.4.0-alpha.N` releases are published to TestPyPI as each redesign phase exits. The `v0.4.0` release on PyPI lands when [`notes/redesign-status.md`](notes/redesign-status.md) reports every phase complete.

## Project status

**Alpha (`0.4.0a0`).** The `0.3.x` line implemented the original constraint-solver thesis; the `0.4.x` line is rebuilding the framework around code-first infrastructure inference per [ADR 028](notes/design/028-code-first-infra-redesign.md). No backwards-compatibility shims are planned — the constraint vocabulary (`Latency`, `Durability`, `AccessPattern`, `@app.handler`, `@app.scale`, `@app.shared`, TOML catalogs) is being removed root and branch.

Roadmap and design decisions: [ADR index](notes/design/).

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
