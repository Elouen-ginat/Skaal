---
hide:
  - navigation
  - toc
---

# Skaal

**Your Python app is your architecture.**

Write classes and functions. Skaal infers the infrastructure, generates the Pulumi, and your primitive classes are the typed clients. Pylance follows every call site straight down to the underlying SDK. One codebase. One mental model. `skaal deploy` knows what to build.

!!! warning "Redesign in progress"

    Skaal is in the middle of a redesign from "Infrastructure as Constraints" to "code-first infrastructure" (`v0.3.x` → `v0.4.0`).

    The new product is described in [ADR 028](https://github.com/Elouen-ginat/Skaal/blob/main/notes/design/028-code-first-infra-redesign.md). The execution plan and live progress live in [ADR 029](https://github.com/Elouen-ginat/Skaal/blob/main/notes/design/029-redesign-foundation-implementation-plan.md) and the [redesign tracker](https://github.com/Elouen-ginat/Skaal/blob/main/notes/redesign-status.md).

    Many of the pages linked from this site still describe the constraint-solver model. They are accurate for `0.3.x` and will be rewritten as Phase 7 of the redesign lands. If you need a stable install today, pin `skaal==0.3.1`.

## What Skaal will be

```python
from skaal import App, Store, BlobStore, Channel, Cron
from pydantic import BaseModel

class User(BaseModel):
    id: str
    email: str

class Users(Store[User]):
    """One table. The class is the table."""
    by_email = "email"

class Avatars(BlobStore):
    """One bucket. The class is the bucket."""

class SignupEvents(Channel[User]):
    """One topic. The class is the topic."""

app = App("acme")

@app.function
async def signup(user: User) -> User:
    await Users.put(user.id, user)
    await SignupEvents.publish(user)
    return user

@app.schedule(Cron("0 * * * *"))
async def hourly_compact() -> None:
    ...
```

The class **is** the typed client. There is no codegen step in the dev loop:

```python
from acme.users import Users

user: User | None = await Users.get("u1")  # Pylance: User | None
await Users.put("u1", user)                # Pylance: (str, User) -> None
```

When you need a backend-specific feature, pin the type and get the real SDK client back, typed:

```python
from skaal.backends.bigquery import BigQuery

class Sales(Relational[Sale, BigQuery], partition_by="occurred_at"):
    transaction_id: str = Field(primary_key=True)

bq = await Sales.native()  # google.cloud.bigquery.Client, in every environment
```

For full HTTP routing, mount any ASGI app — Skaal deploys it; the framework you already know owns the routes:

```python
from fastapi import FastAPI

api = FastAPI()
app.mount("/api", api)
```

## How it works

1. **Declare** classes (`Store[T]`, `BlobStore`, `Channel[T]`, `Relational[T, B]`) and functions (`@app.function`, `@app.schedule`, `@app.job`).
2. **Infer** an environment-independent `InferredPlan` by walking the `App` graph.
3. **Bind** the plan against an environment (`local`, `aws`, `gcp`) using a fixed defaults table the framework owns.
4. **Generate** Pulumi programs, Dockerfiles, and handler entrypoints from the bound plan.
5. **Deploy** via Pulumi. The `skaal.lock` file pins each binding so the next plan is empty unless code changed.

## CLI

```bash
skaal init                      # scaffold a new project
skaal run                       # local: SQLite + filesystem + in-memory channel
skaal map                       # source -> deployed-resource tree
skaal plan --env prod           # diff: code vs lock, or code vs deployed
skaal deploy --env prod         # Pulumi up against AWS or GCP
skaal where <resource>          # cloud-console URL for a deployed resource
skaal trace <log-or-resource>   # source location for a deployed thing
```

Each verb has one job. There is no constraint DSL, no catalog you maintain, and no solver.

## Targets

- **Local** — SQLite, filesystem, in-process channels, async functions, APScheduler.
- **AWS** — DynamoDB, S3, SQS, Lambda, EventBridge, RDS Postgres, Secrets Manager.
- **GCP** — Firestore, GCS, Pub/Sub, Cloud Run, Cloud Scheduler, Cloud SQL, Secret Manager.

The `0.4.0` cut ships AWS first; GCP follows in a `0.4.x` point release.

## Project status

**Alpha (`0.4.0a0`).** The `0.3.x` line implemented the original constraint-solver thesis; the `0.4.x` line is rebuilding the framework around code-first infrastructure inference per [ADR 028](https://github.com/Elouen-ginat/Skaal/blob/main/notes/design/028-code-first-infra-redesign.md). No backwards-compatibility shims are planned.

Roadmap and design decisions: [ADR index on GitHub](https://github.com/Elouen-ginat/Skaal/tree/main/notes/design).
