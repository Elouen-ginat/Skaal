# ADR 028 — Code-First Infrastructure Redesign

**Status:** Proposed
**Date:** 2026-05-12
**Related:** [user_gaps.md](../user_gaps.md), [what_is_needed_for_prod.md](../what_is_needed_for_prod.md), [ADR 002](002-z3-backend-selection.md) (superseded), [ADR 003](003-catalog-toml-format.md) (superseded), [ADR 019](019-simplification-report.md), [ADR 021](021-solver-diagnostics-implementation-plan.md) (superseded)
**Breaking:** Yes. This ADR drops the constraint-solver product entirely. No backward compatibility shims are planned; user-facing code must be rewritten against the new surface.

---

## 1. North star

Skaal is not "Infrastructure as Constraints." Skaal is:

> **A Python framework where the application code _is_ the infrastructure declaration.**
> Write classes, functions, and handlers. Skaal infers the architecture, generates Pulumi (and a local runtime), and gives you typed clients for every primitive — automatically.

The unification claim must be literally true: there is no parallel infra reality. There is no constraint DSL. There is no catalog the user touches. There is no SMT solver weighing options. The shape of the code _is_ the deployment plan.

Everything in this ADR exists to make that claim true and pleasant to live with.

## 2. Why the redesign is necessary

The current product has two conflicting theses sharing one codebase.

1. **Constraint thesis** (Z3 + TOML catalogs + cost minimization). Re-introduces the parallel reality Skaal claims to remove, makes deploys non-deterministic, optimizes the wrong axis (cost) instead of the actual friction (IAM, secrets, env wiring, observability, type-safe clients, local↔cloud parity).
2. **Structural-inference thesis** (decorators, `Store[T]`, Pulumi codegen, local runtime, `Module` composition). Already 60% of the repo; matches the goal; underserved in the Python ecosystem; the slot Encore occupies in TypeScript/Go is wide open in Python.

These two cannot continue to share a codebase. The constraint thesis is corrosive to the structural one: it asks users to think about backends and tiers at exactly the moments the structural thesis is trying to make them stop thinking about backends and tiers.

This ADR commits to thesis #2 and removes thesis #1 root and branch. No backward compatibility shims are planned, because (a) the project is still alpha (0.3.1) and (b) shimming the constraint vocabulary would re-import the very split-brain we are trying to delete.

## 3. The redesigned product, in one screen

```python
from skaal import App, Store, BlobStore, Channel, Cron
from pydantic import BaseModel

class User(BaseModel):
    id: str
    email: str

class Users(Store[User]):
    """One table. The class is the table."""
    by_email = "email"  # declarative secondary index

class Avatars(BlobStore):
    """One bucket. The class is the bucket."""

class SignupEvents(Channel[User]):
    """One topic. The class is the topic."""

app = App("acme")

@app.function
async def signup(user: User) -> User:
    """The function is the unit. Inferred as RPC; auto-exposed on the wire."""
    await Users.put(user.id, user)
    await SignupEvents.publish(user)
    return user

@app.schedule(Cron("0 * * * *"))
async def hourly_compact() -> None:
    ...
```

Calling `signup` from another module is typed end-to-end and identical whether running locally or in the cloud:

```python
from skaal_clients.acme import signup
result: User = await signup(User(id="u1", email="a@b.com"))
```

The user runs:

```bash
skaal run                     # local: SQLite + filesystem + in-memory channel
skaal plan --env prod         # shows the diff: Users → DynamoDB, Avatars → S3, …
skaal deploy --env prod       # Pulumi up against AWS
```

No decorator argument carries a constraint. No HTTP route DSL. No catalog is loaded. No solver runs. The class is the table. The function is the unit of compute and the RPC endpoint. The environment picks the backend by a fixed table.

**When the user really wants HTTP routing**, Skaal does not reinvent FastAPI — it deploys it:

```python
from fastapi import FastAPI

api = FastAPI()

@api.get("/users/{id}")
async def get_user(id: str) -> User:
    return await Users.get(id)

app.mount("/api", api)        # Skaal owns the deploy (API Gateway / Cloud Run);
                              # FastAPI owns routing inside the app.
```

`app.mount(path, asgi_app)` accepts any ASGI application (FastAPI, Starlette, Litestar). Skaal infers it as a single "ASGI service" resource — one Lambda/Cloud Run target — and reserves the path prefix. There is no `@app.handler`, no `Route`, no `APIGateway` user primitive. The routing surface is the framework the user already knows.

## 4. What we drop, what we keep, what we add

### 4.1 Drop (deletions, not migrations)

| Module / surface | Action |
|---|---|
| `skaal/solver/` (entire package) | Delete. |
| `skaal/types/constraints.py`, `skaal/types/solver.py` | Delete. |
| `skaal/types/*` constraint primitives: `Latency`, `Durability`, `AccessPattern`, `Throughput`, `Consistency`, throughput tier constants, cost weights | Delete. Keep only non-constraint types: `Duration`, `TTL`, `Retention`, `Page`, `SecondaryIndex`, `JobSpec/Handle/Result/Status`, `InvokeContext`, `BlobObject`, `RelationalMigration*`. |
| `skaal/catalog/` (TOML loading and models) | Delete. The catalog concept ends. |
| `catalogs/*.toml` (`local.toml`, `aws.toml`, `gcp.toml`) | Delete. |
| `skaal/cli/commands/catalog*.py`, `skaal catalog validate`, `skaal catalog sources` | Delete. |
| `[tool.skaal] extends`, catalog overlay machinery (ADR 022) | Delete. |
| Constraint kwargs on every decorator: `latency=`, `durability=`, `access_pattern=`, `throughput=`, `consistency=`, `read_latency=`, `write_latency=`, `freshness=`, `cost_tier=` | Removed at the parser level. Passing them raises `TypeError` with a one-line migration hint. |
| `skaal solver explain`, solver diagnostics rendering (ADR 021) | Delete. Replaced by `skaal plan --explain` over the deterministic inference. |
| `skaal/agent.py`, `Agent`, `@agent` | Move to `skaal-contrib` repo or delete. Not core to the thesis. |
| `skaal/patterns.py`: `EventLog`, `Outbox`, `Projection`, `Saga`, `SagaStep`, and `skaal/runtime/engines/projection.py`, saga engine, outbox engine | Move to `skaal-contrib` or delete. Each is its own product. |
| `mesh/` Rust crate, `skaal/runtime/mesh_runtime.py` | Quarantine behind an off-by-default feature flag. Not part of the v1 thesis. Revisit only after AWS + GCP code-first inference is undeniably working. |
| `langgraph`, `chromadb`, `pgvector`, `psycopg`, `langchain-*`, `VectorStore` | Remove as core. Move vector tier to optional `skaal[vector]` extra; not in the v1 thesis. |
| `skaal/plugins.py` entry-point system for backends | Delete. Backends become a fixed table indexed by `(primitive_kind, environment)`. Third-party backends re-enter later via a documented protocol but are not v1. |
| `skaal/components.py`: `ExternalStorage`, `ExternalQueue`, `ExternalObservability`, `Proxy`, `AppRef`, `Route`, `ScheduleTrigger`, `APIGateway`, `AuthConfig` | Replace. Most of these exist to paper over the lack of structural inference. The new surface infers them. See §6.4. |
| `@app.handler` decorator (and its `__skaal_handler__` metadata) | Delete. `@app.function` is the only callable primitive (§6.4). HTTP exposure of a function is automatic; full REST routing happens via `app.mount("/api", fastapi_app)` and Skaal deploys the ASGI app behind the cloud's HTTP edge. |
| `@app.scale` decorator | Delete. Replaced by per-function kwargs on `@app.function` (`min_concurrency`, `max_concurrency`) and per-environment overrides. |
| `@app.shared` decorator | Delete. It was a constraint-era hint about sharing backends across resources; the binding layer now decides identity by `(ResourceKind, BackendId, env)` deterministically. |
| `skaal/api.py` Python equivalents of CLI verbs | Keep verbs that survive (`run`, `plan`, `deploy`, `build`, `init`); drop verbs that vanish with the solver. |

### 4.2 Keep (shape preserved, internals refactored)

| Module / surface | Notes |
|---|---|
| `skaal/app.py`, `skaal/module.py` (`App`, `Module`, `app.include(...)`) | Composition model is correct. Internals updated to use the inference pipeline (§6) instead of the solver. |
| `skaal/decorators.py` — only `@app.storage`, `@app.function` (rename of `@app.compute`), `@app.schedule`, `@app.job`, `@app.external` survive | Surface kept. Constraint arguments removed; replaced with the small, environment-aware override knobs in §6.5. `@app.handler`, `@app.scale`, `@app.shared` are deleted (see §4.1). |
| `skaal/storage.py` (`Store[T]`), `skaal/blob.py` (`BlobStore`), `skaal/channel.py` (`Channel[T]`), `skaal/relational.py` | Kept. These are the typed primitives that the inference treats as "I want a database/bucket/topic." |
| `skaal/runtime/local.py` (Starlette + Uvicorn) | Kept. Becomes the canonical dev experience; the only "local target." |
| `skaal/deploy/templates/` (Pulumi programs, Dockerfile, handler entrypoints, Jinja2) | Kept. The deploy artifact pipeline is real and good. Templates updated to consume the new inferred-plan shape. |
| `skaal/migrate/` (6-stage schema migrations) | Kept, but driven by inferred schema rather than constraints. |
| `skaal/schedule.py` (`Cron`, `Every`, `Schedule`) | Kept. |
| `skaal/secrets/` (AWS + GCP secret injection, ADR 024) | Kept. |
| `skaal/sync.py` | Kept. |
| `skaal/cli/` (`typer`-based CLI) | Restructured. Verbs in §7. |
| `skaal/backends/` for the **defaults table** (sqlite, postgres, redis, dynamodb, firestore, filesystem-blob, s3, gcs, local-channel, redis-channel) | Kept as implementations. Selection collapses to a lookup, not a search. |

### 4.3 Add (the genuinely new mechanisms)

1. **Environments** as the only tier axis users see (`local`, `cloud`, plus user-named environments like `staging`, `prod`, `prod-eu`).
2. **A fixed, per-primitive, per-environment defaults table** — not a search, not a catalog, just a table the framework owns. The user opts in to overriding a single binding when they need to.
3. **Generated typed clients** the moment a `Store[T]` / `BlobStore` / `Channel[T]` / `@app.function` is declared, importable from anywhere in the codebase.
4. **`skaal plan` as a deterministic, human-readable diff** between the code's implied architecture and (a) the local runtime view or (b) the deployed reality for an environment.
5. **A "what did my code become?" view** (`skaal map`) — a tree mapping source symbols to deployed primitives, rendered in the CLI and emitted as machine-readable JSON for IDE/PR integrations.
6. **PR-level infra diffs** — a GitHub Action that runs `skaal plan --env prod` against the merge base and posts the rendered diff as a sticky PR comment.
7. **Explicit pin-on-first-deploy.** Once a primitive is bound to a backend in an environment, the binding is persisted in `skaal.lock` and held until the user changes it. No silent re-architecting.
8. **Bidirectional traceability** between source and deployed resources via embedded resource tags (`skaal:source=<module>:<lineno>`) and a `skaal where <resource>` / `skaal trace <log-line>` CLI.
9. **A single override vocabulary** (`@app.storage(backend="redis")`, `@app.compute(memory_mb=1024)`) used everywhere — same words for local override, env-specific override, and global override.

## 5. Reference designs and what we steal from each

- **Encore (gold standard).** Steal: structural inference of services, automatic tracing, infra diffs in PRs, the developer flow ("write code, see infra appear"), RPC ergonomics between modules.
- **Modal.** Steal: `@app.function` packaging UX (no Dockerfile thinking for the common case), warm-pool semantics for the local runtime.
- **Convex.** Steal: end-to-end type safety from declaration to client call site.
- **Cloudflare Workers + Durable Objects.** Steal: "your class is the actor is the deployed unit" pattern, but only later (post-v1) — agents/actors are not v1.
- **Wing.** Take as a cautionary tale: stay in Python. No new language. No new file extension.

## 6. The new architecture, layer by layer

### 6.1 Layer map

```
  ┌──────────────────────────────────────────────────────────────┐
  │ Layer 1 — Primitives (typed, structural)                     │
  │   App, Module, Store[T], BlobStore, Channel[T],              │
  │   Relational, @app.function, @app.schedule, @app.job         │
  ├──────────────────────────────────────────────────────────────┤
  │ Layer 2 — Inference                                          │
  │   Walks the App graph, produces an `InferredPlan`:           │
  │     resources, relationships, env-independent.               │
  ├──────────────────────────────────────────────────────────────┤
  │ Layer 3 — Binding                                            │
  │   InferredPlan + Environment + skaal.lock → `BoundPlan`:     │
  │     each resource bound to one concrete backend.             │
  │   Pure table lookup. No search. No SMT.                      │
  ├──────────────────────────────────────────────────────────────┤
  │ Layer 4 — Codegen + Runtime                                  │
  │   BoundPlan → Pulumi program (cloud) or in-process runtime   │
  │   (local). Same BoundPlan drives both, by design.            │
  ├──────────────────────────────────────────────────────────────┤
  │ Layer 5 — Typed clients                                      │
  │   InferredPlan → generated Python module                     │
  │   `skaal_clients/` injected into the dev path, importable    │
  │   so `Users.get(...)` is typed end-to-end with no manual     │
  │   wiring.                                                    │
  ├──────────────────────────────────────────────────────────────┤
  │ Layer 6 — Diff + trace                                       │
  │   BoundPlan ↔ deployed-state ↔ source map = `skaal plan`,    │
  │   `skaal map`, `skaal where`, `skaal trace`, PR comment.     │
  └──────────────────────────────────────────────────────────────┘
```

Each layer has a single, named output. Layers above the line are user-authored; layers below are framework-owned. Nothing in this stack is a search.

### 6.2 The `InferredPlan`

A deterministic, environment-independent **pydantic model** produced by walking `App` and its modules. The whole inference surface is pydantic — no raw `dict`, no `dataclass`, no untyped tuples — so the JSON-schema, validation, equality, and `model_dump_json()` paths come for free and are usable from tests, the CLI, and editor extensions:

```python
from pydantic import BaseModel, ConfigDict, Field

class SourceLocation(BaseModel):
    model_config = ConfigDict(frozen=True)
    module: str                          # e.g. "acme.users"
    qualname: str                        # e.g. "Users" or "signup"
    file: str                            # absolute path at inference time
    line: int

class SchemaRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    model_qualname: str                  # pydantic model used for the resource
    fingerprint: str                     # hash of model_json_schema()

class ResourceOverrides(BaseModel):
    """The only knobs allowed at declaration sites (§6.5)."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    backend: str | None = None           # name from the registry (§6.12)
    region: str | None = None
    memory_mb: int | None = None
    timeout_s: float | None = None
    min_concurrency: int | None = None
    max_concurrency: int | None = None

class Edge(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_id: str
    target_id: str
    kind: Literal["reads", "writes", "publishes", "subscribes", "invokes"]

class ResourceKind(StrEnum):
    STORE = "store"
    RELATIONAL = "relational"
    BLOB = "blob"
    CHANNEL = "channel"
    FUNCTION = "function"
    ASGI_SERVICE = "asgi_service"        # produced by app.mount(path, asgi_app)
    SCHEDULE = "schedule"
    JOB = "job"
    SECRET = "secret"

class InferredResource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str                              # stable, derived from module + qualname
    kind: ResourceKind
    source: SourceLocation
    schema_: SchemaRef | None = Field(default=None, alias="schema")
    indexes: tuple[SecondaryIndex, ...] = ()
    overrides: ResourceOverrides = ResourceOverrides()

class InferredPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    app: str
    resources: tuple[InferredResource, ...]
    edges: tuple[Edge, ...]
    fingerprint: str                     # hash of model_dump_json(by_alias=True)
```

Properties this enforces:

1. **Deterministic.** `InferredPlan.fingerprint` is computed from `model_dump_json(by_alias=True, exclude={"fingerprint"})` over a canonically-sorted resource tuple. Byte-stable across reorderings; PR-level diffs use it.
2. **Environment-independent.** No env name appears. No backend names appear. Just shapes.
3. **Source-tagged.** Every resource carries its source location, which becomes a Pulumi tag, a runtime log field, and the answer to `skaal where <resource>`.
4. **Schema-exportable.** `InferredPlan.model_json_schema()` is the contract for editor plugins, CI tools, and the GitHub Action — no hand-rolled JSON adapter layer.

### 6.3 The `BoundPlan` and the defaults table

`BoundPlan = bind(InferredPlan, environment, lock)`. Every type involved is a frozen pydantic model — `BoundResource`, `BoundPlan`, `Environment`, `EnvProfile`, `LockFile`, `LockEntry`. The binding step is a pure function:

```python
from pydantic import BaseModel, ConfigDict

class EnvProfile(StrEnum):
    LOCAL = "local"
    CLOUD_AWS = "cloud-aws"
    CLOUD_GCP = "cloud-gcp"

class EnvironmentBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    backend: str
    region: str | None = None
    options: dict[str, str] = {}         # backend-specific knobs (string-only, typed at the backend layer)

class Environment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    profile: EnvProfile
    region: str | None = None
    bindings: dict[str, EnvironmentBinding] = {}   # resource_id -> override
    telemetry: TelemetryConfig | None = None
    secrets: SecretsConfig | None = None

class LockEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    backend: str
    region: str | None = None
    pinned_at: datetime
    pinned_by: str | None = None
    fingerprint: str                     # InferredResource fingerprint at bind time

class LockFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = 1
    entries: dict[tuple[str, str], LockEntry] = {}  # (env_name, resource_id) -> entry

class BoundResource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    inferred: InferredResource
    backend: str
    region: str | None = None
    options: dict[str, str] = {}
    pinned: bool                         # True iff served from the lock

class BoundPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    app: str
    environment: str
    resources: tuple[BoundResource, ...]
    edges: tuple[Edge, ...]

def bind(plan: InferredPlan, env: Environment, lock: LockFile) -> BoundPlan:
    bound = tuple(bind_resource(r, env, lock) for r in plan.resources)
    return BoundPlan(app=plan.app, environment=env.name, resources=bound, edges=plan.edges)

def bind_resource(res: InferredResource, env: Environment, lock: LockFile) -> BoundResource:
    if (env.name, res.id) in lock.entries:                       # 1. lock wins
        e = lock.entries[(env.name, res.id)]
        return BoundResource(inferred=res, backend=e.backend, region=e.region, pinned=True)
    if res.id in env.bindings:                                   # 2. env override
        b = env.bindings[res.id]
        return BoundResource(inferred=res, backend=b.backend, region=b.region, options=b.options, pinned=False)
    if res.overrides.backend is not None:                        # 3. declaration-site override
        return BoundResource(inferred=res, backend=res.overrides.backend, region=res.overrides.region, pinned=False)
    return BoundResource(                                        # 4. defaults table
        inferred=res,
        backend=DEFAULTS[res.kind][env.profile],
        region=env.region,
        pinned=False,
    )
```

The defaults table is a `Mapping[ResourceKind, Mapping[EnvProfile, str]]` literal checked into `skaal/binding/defaults.py`. Initial contents:

| Resource kind | `local` | `cloud-aws` | `cloud-gcp` |
|---|---|---|---|
| `STORE` (KV) | `sqlite` | `dynamodb` | `firestore` |
| `RELATIONAL` | `sqlite` | `rds-postgres` | `cloud-sql-postgres` |
| `BLOB` | `filesystem-blob` | `s3` | `gcs` |
| `CHANNEL` | `in-process` | `sqs` | `pubsub` |
| `FUNCTION` | `asyncio` | `lambda` | `cloud-run` |
| `ASGI_SERVICE` | `uvicorn` | `apigw + lambda` | `cloud-run` |
| `SCHEDULE` | `apscheduler` | `eventbridge → lambda` | `cloud-scheduler → cloud-run` |
| `JOB` | `apscheduler` | `sqs + lambda worker` | `cloud-tasks + cloud-run` |
| `SECRET` | `.env file` | `aws-secrets-manager` | `gcp-secret-manager` |

The table is the contract. It changes only via ADR. There is no per-tenant tuning. There is no "see what the solver picked." If you want something other than the default, you say so in one line (§6.5).

### 6.4 What replaces `components.py` and `@app.handler`

Most of the `components.py` types — and `@app.handler` itself — existed to compensate for missing structural inference. The redesign removes them and either infers the role or hands routing back to the framework the user already knows (FastAPI/Starlette/Litestar). **Skaal does not own URL routing.**

| Old | New |
|---|---|
| `@app.handler("POST /signup")` decorator | Removed. `@app.function` is the only callable primitive. A `@app.function` with pydantic in/out is automatically reachable via (a) the typed RPC client (§6.6) and (b) a wire endpoint at a derived URL (`POST /<module>/<function_name>`, JSON body). The user never authors a route string. |
| `APIGateway(...)` mounted in `App` | Inferred. Each environment gets exactly one HTTP edge per ASGI service. Functions ride on a generated dispatch handler; mounted ASGI apps each get their own edge. |
| `Route(...)` | Deleted. For function endpoints the URL is derived; for full REST the route lives inside the mounted ASGI app (`@api.get("/users/{id}")` in FastAPI). |
| `AuthConfig`, `AuthMethod` | Two cases. (1) For functions: `@app.function(auth=Bearer())`. (2) For mounted ASGI apps: the user configures auth using FastAPI/Starlette middleware — Skaal does not interpose. |
| `ExternalStorage(...)` | Replaced by an explicit `@app.external(...)` decorator on a tiny adapter class declaring schema + endpoint. Same shape as `Store[T]`, but binds to a user-provided connection. |
| `ExternalQueue(...)` | Same — declared as a `Channel[T]` subclass with `external=...` parameter or a peer `@app.external_channel`. |
| `ExternalObservability` | Folded into environment config (`Environment.telemetry`), not a primitive in the app. |
| `Proxy`, `AppRef`, `ScheduleTrigger` | Removed. The trigger of a scheduled function is the `@app.schedule(...)` decorator on it. Cross-app references happen via Python imports between modules, which the inference picks up automatically. |

#### 6.4.1 The two callable shapes the framework recognises

```python
# Shape 1 — a function. The unit of compute. Auto-RPC.
@app.function
async def signup(user: User) -> User: ...

@app.function(memory_mb=1024, timeout_s=30, auth=Bearer())
async def heavy_job(input: JobInput) -> JobOutput: ...

# Shape 2 — a mounted ASGI service. Skaal deploys it; the user owns routing inside.
from fastapi import FastAPI
api = FastAPI()
app.mount("/api", api)
```

These are the only two ways to put compute in an app. Both are inferred as resources (`FUNCTION` or `ASGI_SERVICE`); both bind through the defaults table; both get the same tagging, secrets, telemetry, and PR-diff treatment. Neither requires the user to learn a Skaal-specific routing DSL.

### 6.5 The override vocabulary (the entire user-facing tuning surface)

Three knobs. That's the whole API for "I want something other than the default."

1. **Resource-local override** — at the declaration site:

   ```python
   class Users(Store[User], backend="redis"):
       ...

   @app.function(memory_mb=1024, timeout_s=30)
   async def signup(user: User) -> User: ...
   ```

   `backend=` accepts only names registered for that `ResourceKind` (§6.12); passing an unknown or kind-incompatible name fails at import time with the list of valid names.

2. **Environment override** — in `skaal.toml`:

   ```toml
   [env.prod]
   profile = "cloud-aws"
   region = "eu-west-1"

   [env.prod.bindings]
   "acme.users:Users"   = "dynamodb"
   "acme.users:Avatars" = { backend = "s3", region = "us-east-1" }
   ```

3. **Per-invocation client overrides** — for tests and one-offs, the typed client accepts an explicit binding:

   ```python
   from skaal_clients.acme.users import Users
   await Users.bind(memory_backend).put("u1", user)   # only in tests
   ```

Anything beyond these three knobs is a sign the user is trying to express a constraint, which is the product we just deleted. The defaults table absorbs the rest.

#### 6.5.1 Worked example — switching `Relational` from Postgres to BigQuery

A frequent real question: "I want `class Sales(Relational)` to live on BigQuery in my analytics environment, but on Postgres in dev." Three concrete ways to express it, all using the same three knobs:

```python
# acme/sales.py
from datetime import datetime
from decimal import Decimal
from skaal import Relational
from sqlmodel import Field

# Option A — pin at the declaration site. Sticks across every environment
# unless a later override re-pins it. Use when the model is BigQuery-shaped
# by nature (append-only, no row updates, partitioned by `occurred_at`).
class Sales(Relational, backend="bigquery", partition_by="occurred_at"):
    transaction_id: str = Field(primary_key=True)
    amount: Decimal
    occurred_at: datetime
```

```python
# Option B — keep the class plain, override per environment.
class Sales(Relational):
    transaction_id: str = Field(primary_key=True)
    amount: Decimal
    occurred_at: datetime
```

```toml
# skaal.toml — same code; Postgres in dev, BigQuery in the warehouse env.
[env.dev]
profile = "cloud-aws"

[env.warehouse]
profile = "cloud-gcp"
region  = "EU"

[env.warehouse.bindings]
"acme.sales:Sales" = { backend = "bigquery", options = { dataset = "acme_warehouse", partition_by = "occurred_at" } }
```

```bash
# Option C — moving an already-deployed binding. Updates skaal.lock and
# generates the migration step Pulumi will run.
$ skaal rebind --env warehouse acme.sales:Sales bigquery
```

What makes any of this work is **one registered backend**: `bigquery`, in the same `skaal/binding/registry.py` (§6.12) that lists `postgres`, `sqlite`, `dynamodb`, etc. The registry entry declares the `ResourceKind`s it satisfies and the feature flags it supports; without a matching entry, the framework rejects `backend="bigquery"` at import time with a pointer to `skaal backends list`. There is no TOML catalog and no entry-point plugin layer — adding a new backend is one Python module plus one registry line.

#### 6.5.2 Kinds, not just names — why BigQuery is not a drop-in for Postgres

`Relational` covers two distinct workload shapes: OLTP (row-level reads/updates, transactions) and analytics (append-mostly, columnar scans). The registry encodes this by tagging each backend with the kinds it *actually* supports:

| Backend | Kinds satisfied |
|---|---|
| `postgres` | `relational-oltp`, `relational-analytics` (modest scale) |
| `cloud-sql-postgres` | `relational-oltp`, `relational-analytics` (modest scale) |
| `sqlite` | `relational-oltp` (single-writer) |
| `bigquery` | `relational-analytics` |
| `redshift` (future) | `relational-analytics` |

A `Relational` class infers its required kinds from its declaration: a `primary_key` plus calls to `.update(...)` or `.delete(...)` in the codebase mark it as `relational-oltp`; append-only with `partition_by=...` and `@app.function` query patterns mark it `relational-analytics`. If the user binds `backend="bigquery"` to a class the inference flagged as OLTP-shaped, import fails with:

```
RelationalKindMismatch: acme.sales:Sales is bound to 'bigquery' which supports
  {relational-analytics}, but the class uses row-level update() at
  acme/sales.py:42. Either remove the row-level mutation or pick a backend
  in {postgres, cloud-sql-postgres}.  See `skaal backends list --kind relational-oltp`.
```

This is the only place the framework gets opinionated about workload semantics. It is deterministic, source-located, and uses the same vocabulary as the rest of the override system.

### 6.6 Generated typed clients

When `skaal run`, `skaal plan`, or `skaal build` runs, the framework emits a `skaal_clients/` package alongside the user's source. It contains:

- One module per declared `Store[T]`/`BlobStore`/`Channel[T]`/`Relational` with fully typed methods derived from the pydantic schema and declared secondary indexes.
- One module per `@app.function` exposing a typed RPC client (`signup(user: User) -> User`), so other Python modules can call functions without restating the wire shape and without importing the implementation directly.
- A `manifest.json` (validated by a pydantic `ClientManifest` model) for IDE plugins and tooling.

Notably absent: any client for mounted ASGI services. If the user mounts FastAPI via `app.mount("/api", fastapi_app)`, the client surface for that subtree is whatever FastAPI provides (e.g. its own OpenAPI-generated clients). Skaal does not double-generate over a routing framework it doesn't own; that would be the exact mistake `@app.handler` was making.

The generation step is incremental, fast (< 200 ms for small apps), and idempotent. The package is git-ignored by default; users opt in to committing it. `skaal run` re-generates on import; `skaal plan` re-generates as a side effect; `skaal build` emits the same package into the artifact.

Crucially, the typed-client surface is the same shape whether the binding is local SQLite or cloud DynamoDB — the runtime swaps the backend transparently. The user never imports a backend.

### 6.7 `skaal plan` as a diff, not a JSON dump

The current `skaal plan` writes a JSON `PlanFile`. The redesigned `skaal plan` outputs a structured diff. There are two diff modes:

1. **Structural diff** (default): `BoundPlan(now) − BoundPlan(lock)`. "These resources are new. These changed shape. These were removed."
2. **State diff** (`--against=deployed`): `BoundPlan(now) − DeployedState(env)`. "Cloud has this, your code says that, here's the delta."

Output is a tree with one line per resource, color-coded for add/change/remove, plus an `--explain` flag that drills into a single resource: why was `Users` bound to `dynamodb`? Answer is always one of: lock pinned it; env override; default table. Never a solver trace.

JSON is still emitted at `.skaal/plan.json` for programmatic consumers, but it is no longer the user-facing artifact.

### 6.8 `skaal map` — "what did my code become?"

A read-only command that prints the source-to-resource mapping:

```
acme/
├─ users.py
│  ├─ class Users(Store[User])             →  dynamodb table "acme-prod-users"
│  └─ class Avatars(BlobStore)             →  s3 bucket "acme-prod-avatars"
├─ functions.py
│  └─ async def signup(...)                →  lambda "acme-prod-signup" (apigw POST /acme.functions/signup)
├─ api.py
│  └─ app.mount("/api", FastAPI())         →  lambda "acme-prod-api" (apigw /api/*)
└─ jobs.py
   └─ hourly_compact [cron "0 * * * *"]    →  eventbridge → lambda "acme-prod-hourly-compact"
```

It is also emitted as `.skaal/map.json` (validated by a pydantic `ResourceMap` model) for editor extensions (VS Code, JetBrains) to render gutter icons and "go to deployed resource" actions.

### 6.9 PR-level diffs

A first-party GitHub Action (`skaal-ci/plan-action@v1`) runs:

```
skaal plan --env prod --base=origin/main --format=github-markdown
```

…and posts the rendered structural diff as a sticky PR comment. This is the moment users fall in love with the product, per the report. It must work on day one of v1.

### 6.10 `skaal.lock` (pin-on-first-deploy)

Format: TOML, committed. Written by `skaal deploy` after a successful provision. Reads roughly:

```toml
[env.prod.bindings."acme.users:Users"]
backend = "dynamodb"
pinned_at = "2026-05-12T14:00:00Z"
pinned_by = "alice@acme.com"

[env.prod.bindings."acme.users:Avatars"]
backend = "s3"
pinned_at = "2026-05-12T14:00:00Z"
```

Rules:

- A binding may move only when the user explicitly migrates: `skaal rebind --env prod acme.users:Users redis`. This writes both the new binding and the migration step Pulumi must run.
- Removing a binding requires `skaal unbind`. There is no silent drop.
- The lock file is the source of truth for "what is currently in the cloud," used by every `--against=deployed` diff path.

### 6.11 Traceability

Every Pulumi resource is tagged on creation with:

```
skaal:app          = "acme"
skaal:env          = "prod"
skaal:source       = "acme.users:Users"
skaal:source_line  = "acme/users.py:14"
skaal:fingerprint  = "<InferredResource fingerprint>"
```

These tags drive two new CLI verbs:

- `skaal where acme.users:Users` → the AWS/GCP console URL for the resource.
- `skaal trace <log-line-or-resource-id>` → the source location that became that resource.

Runtime logs include the same `skaal:source` field on every emitted log record, closing the loop.

### 6.12 The backend registry (replaces the catalog and the plugin layer)

A single Python module — `skaal/binding/registry.py` — owns the list of every backend Skaal knows. It is built and exposed as a pydantic model so the same data structure powers the binder, `skaal backends list`, and the import-time validation that rejects bad `backend=` overrides:

```python
class BackendCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ttl: bool = False
    secondary_indexes: bool = False
    transactions: bool = False
    streaming: bool = False
    row_updates: bool = False
    partitioning: bool = False
    # …add only as a kind genuinely requires it.

class BackendEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str                            # "postgres", "bigquery", "redis", …
    kinds: frozenset[str]                # {"relational-oltp", "relational-analytics"}
    profiles: frozenset[EnvProfile]      # which env profiles can pick it
    capabilities: BackendCapabilities
    impl_path: str                       # dotted path to the implementation class
    options_schema: type[BaseModel]      # pydantic schema for backend-specific options

REGISTRY: tuple[BackendEntry, ...] = (
    BackendEntry(name="postgres",  kinds={"relational-oltp", "relational-analytics"}, profiles={LOCAL, CLOUD_AWS}, …),
    BackendEntry(name="bigquery",  kinds={"relational-analytics"},                    profiles={CLOUD_GCP},        …),
    BackendEntry(name="dynamodb",  kinds={"store"},                                   profiles={CLOUD_AWS},        …),
    BackendEntry(name="firestore", kinds={"store"},                                   profiles={CLOUD_GCP},        …),
    BackendEntry(name="s3",        kinds={"blob"},                                    profiles={CLOUD_AWS},        …),
    # …
)
```

Rules the registry enforces (all at import time, all with source-located errors):

1. Every `backend=` override resolves to exactly one `BackendEntry`. Unknown names → `UnknownBackendError` listing valid alternatives.
2. The chosen entry's `kinds` must include every kind the inferred resource requires (§6.5.2). Otherwise → `BackendKindMismatch` with the offending source line.
3. The entry must include the active `Environment.profile` in `profiles`. Otherwise → `BackendNotAvailableInProfile`.
4. Backend-specific options (`partition_by=`, `dataset=`, …) are validated against `options_schema`. No untyped option dicts cross the binding boundary.

The registry is a static module. Adding a new backend is one PR that adds an implementation file, one `BackendEntry`, and one test. There is no entry-point discovery, no TOML catalog overlay, no per-environment plugin set. Third-party backends re-enter in a later version through a documented `BackendProtocol` plus a registration call; the registry's data shape is already designed to admit them.

## 7. The new CLI

Trimmed to what fits the thesis. Each verb has one clear job.

| Verb | Purpose |
|---|---|
| `skaal init` | Scaffold a new project. Writes `skaal.toml` with one env (`local`) and a starter `app.py`. |
| `skaal run` | Start the local runtime. Hot reload by default in TTY. Regenerates `skaal_clients/`. |
| `skaal map` | Print the source → resource tree for an environment. |
| `skaal plan [--env <name>] [--against=deployed]` | Print the structural or state diff. |
| `skaal deploy --env <name>` | Provision via Pulumi. Updates `skaal.lock`. |
| `skaal build --env <name>` | Emit artifacts (Pulumi program, Dockerfiles, handler entrypoints) without provisioning. |
| `skaal rebind --env <name> <resource> <backend>` | Move a pinned binding. Generates migration steps. |
| `skaal unbind --env <name> <resource>` | Remove a pinned binding (resource is being deleted). |
| `skaal where <resource> [--env <name>]` | Open the cloud-console URL for a deployed resource. |
| `skaal trace <log-or-resource>` | Print the source location for a deployed resource or log line. |
| `skaal backends list [--kind <k>] [--profile <p>]` | Print every backend the registry knows, with its supported kinds and profiles. Discovery surface for `backend=` overrides. |
| `skaal doctor` | Sanity-check toolchain (pulumi, docker, cloud credentials). |

Removed verbs: `skaal catalog *`, `skaal solver *`, `skaal explain` (folded into `skaal plan --explain`).

## 8. New public API surface (canonical)

`skaal/__init__.py` `__all__` shrinks materially. The keep list:

```
App, Module, ModuleExport,
Store, BlobStore, Channel, Relational,
Cron, Every, Schedule, ScheduleContext,
Secret, SecretRegistry,
Duration, TTL, Retention, Page, SecondaryIndex,
JobSpec, JobHandle, JobResult, JobStatus,
InvokeContext, BeforeInvoke,
RetryPolicy, RateLimitPolicy, CircuitBreaker, Bulkhead,
ensure_relational_schema, open_relational_session,
sync_run,
```

The keep list also adds the renamed/new decorator and the registry's user-discoverable surface:

```
function,                       # was: compute / handler — the single callable primitive
external, external_channel,     # explicit adapters for user-owned external resources
BackendEntry, BackendCapabilities  # read-only types, exposed for `skaal backends list` consumers
```

The drop list (removed from public API entirely, no deprecation alias):

```
handler, scale, shared,         # @app.handler / @app.scale / @app.shared decorators
Agent, agent,
APIGateway, AuthConfig, AppRef, ExternalObservability, ExternalQueue,
  ExternalStorage, Proxy, Route, ScheduleTrigger,
EventLog, Outbox, Projection, Saga, SagaStep,
VectorStore,
TelemetryConfig (becomes env-level config),
EngineTelemetrySnapshot, ReadinessState (runtime-internal),
RelationalMigration* (kept internal to skaal.migrate),
```

The constraint-vocabulary types (`Latency`, `Durability`, `AccessPattern`, `Throughput`, `Consistency`) never appear in the new `__all__` and their modules are deleted. Every model that survives in the public surface is a pydantic `BaseModel`; no public type is a `dataclass` or untyped `dict`.

## 9. Implementation phases

Each phase produces a runnable, releasable artifact. No phase is allowed to leave the tree in a state where both old and new surfaces are simultaneously exposed.

### Phase 0 — Branch, version, and rename (0.5 week)

1. Cut a `v0.4.0-alpha` branch from `main`. The redesign lands as 0.4.x. Marketing rename happens at 0.4.0.
2. Update `pyproject.toml` description, README hero, and `docs/index.md` to the new pitch (§3).
3. Delete the README sentence "Infrastructure as Constraints" and all derivatives.
4. Update `CITATION.cff`, license stays GPL-3.0 (separate ADR for relicensing).

### Phase 1 — Delete the constraint product (1 week)

1. Delete `skaal/solver/`, `skaal/catalog/`, `catalogs/`, `skaal/types/constraints.py`, `skaal/types/solver.py`, and the constraint primitives in `skaal/types/`.
2. Delete `skaal/cli/commands/catalog*.py`, the `solver` subcommands, the `explain` command.
3. Delete the constraint kwargs from `skaal/decorators.py`. Rename `compute` → `function`. Delete `handler`, `scale`, `shared` decorators outright. Replace the parser with the strict allow-list of override knobs (§6.5).
4. Delete `skaal/plugins.py`. Replace by a hardcoded backend dispatch in `skaal/binding/registry.py`.
5. Delete `skaal/agent.py`, `skaal/patterns.py`, `skaal/runtime/engines/`, `skaal/vector.py`, `skaal/runtime/mesh_runtime.py`, the `mesh/` Rust crate (move to an archive branch).
6. Delete `skaal/components.py` user-facing types (`APIGateway`, `Route`, `AuthConfig`, `Proxy`, `AppRef`, `ScheduleTrigger`, `ExternalObservability`); keep `ExternalStorage` / `ExternalQueue` only long enough to be reshaped into `@app.external` in Phase 2.
7. Run `make lint && make typecheck && make test`. Expect mass failures; this phase ends when the tree compiles with deletions complete and the test suite is reduced to the surviving surface.

Exit criterion: `grep -r "Constraint\|Latency\|Durability\|AccessPattern\|Throughput\|Catalog\|@app\.handler\|@app\.scale\|@app\.shared" skaal/` returns zero hits outside of comments referencing this ADR.

### Phase 2 — Build the inference layer (1.5 weeks)

1. New package `skaal/inference/`:
   - `walk.py` — walks `App._collect_all()` and produces `InferredResource` instances.
   - `model.py` — pydantic models (`InferredPlan`, `InferredResource`, `Edge`, `SchemaRef`, `SourceLocation`, `ResourceOverrides`, `ResourceKind`). All `model_config = ConfigDict(frozen=True, extra="forbid")`.
   - `fingerprint.py` — stable hash via `model_dump_json(by_alias=True)` over canonically-sorted tuples.
   - `asgi.py` — recogniser that turns `app.mount(path, asgi_app)` calls into `ASGI_SERVICE` resources without inspecting the mounted app's routes.
2. Convert every surviving decorator (`@app.storage`, `@app.function`, `@app.schedule`, `@app.job`, `@app.external`) to populate a single `__skaal_inferred__` attribute holding an `InferredResource` instance instead of the per-decorator `__skaal_storage__` / `__skaal_compute__` / etc. dunder family.
3. Add `tests/inference/test_fingerprint.py` asserting byte-stability across reorderings, and `tests/inference/test_pydantic.py` asserting every public inference type round-trips through `model_dump_json` / `model_validate_json`.

Exit criterion: `App.infer() -> InferredPlan` returns a complete plan for every example under `examples/`, and `InferredPlan.model_json_schema()` is published as the contract artifact.

### Phase 3 — Build the binding layer (1 week)

1. New package `skaal/binding/`:
   - `defaults.py` — the `Mapping[ResourceKind, Mapping[EnvProfile, str]]` literal from §6.3.
   - `environment.py` — pydantic `Environment`, `EnvProfile`, `EnvironmentBinding`; `skaal.toml` loader via `Environment.model_validate(...)`.
   - `lock.py` — pydantic `LockFile`, `LockEntry`; round-trips through `model_dump(mode="json")` for stable TOML emission.
   - `bind.py` — pure `bind(InferredPlan, Environment, LockFile) -> BoundPlan` (all pydantic).
   - `registry.py` — pydantic `BackendEntry`, `BackendCapabilities`, and the `REGISTRY` tuple from §6.12; replaces `skaal/plugins.py`. Adds kind/profile/option validation at import time.
2. `skaal.toml` schema: one section per environment, no catalog references; validated against `Environment`.

Exit criterion: `bind(infer(app), env, lock)` produces a `BoundPlan` whose every resource has exactly one backend, deterministically, for every example, and `pytest --strict-markers tests/binding/` is green.

### Phase 4 — Rewire runtime and deploy on `BoundPlan` (1.5 weeks)

1. `skaal/runtime/local.py` takes `BoundPlan` (not `PlanFile`). The factory that "patches storage backends" becomes a pure consumer of `BoundPlan.resources`.
2. `skaal/deploy/` builders take `BoundPlan` and emit Pulumi programs without any reference to catalog or solver.
3. Update every Jinja2 template under `skaal/deploy/templates/` to read the `BoundPlan` shape.
4. Resource tagging from §6.11 lands in every deploy backend.

Exit criterion: `skaal run` + `skaal deploy --env prod` work end-to-end against AWS for `examples/todo_api` and `examples/counter`.

### Phase 5 — Typed client generation (1 week)

1. New package `skaal/clients/`:
   - `generate.py` — `InferredPlan → skaal_clients/` (Python source emission).
   - `templates/` — Jinja2 templates for `Store[T]` / `BlobStore` / `Channel[T]` / `Relational` / `@app.function` clients. Explicitly no template for mounted ASGI apps — those keep whatever client the user's routing framework already provides.
   - `manifest.py` — pydantic `ClientManifest` written to `skaal_clients/manifest.json`; consumed by IDE plugins.
2. Wire generation into `skaal run` (on reload), `skaal plan` (as a side effect), `skaal build` (into the artifact).
3. Add `.gitignore` advice for `skaal_clients/` in `skaal init` scaffolding.

Exit criterion: in `examples/todo_api`, `from skaal_clients.todos import Todos` is typed end-to-end and works both locally (sqlite) and on AWS (dynamodb).

### Phase 6 — Plan diff, map, where, trace (1 week)

1. `skaal plan` rewritten as a diff against `LockFile` or live deployed state.
2. `skaal map` implementation, JSON emission to `.skaal/map.json`.
3. `skaal where` and `skaal trace` against Pulumi-emitted tags.
4. PR-comment Markdown renderer.

Exit criterion: opening a PR that adds a new `Store[T]` posts the diff comment automatically via the Action in §6.9.

### Phase 7 — Docs, examples, migration guide (0.5 week)

1. Rewrite `docs/index.md`, `docs/quickstart.md`.
2. Examples: keep `counter`, `todo_api`, `hello_world`; delete agent/saga examples; add one Modal-style "function-only" example and one Convex-style "typed client across modules" example.
3. Write a one-page "Skaal 0.3 → 0.4" migration guide (constraint kwargs → backend overrides; remove catalogs; new CLI verbs). This is the user-facing migration story.
4. Update `CLAUDE.md` to remove all constraint-solver language.

Exit criterion: a new user can go from `pip install skaal` to a deployed AWS app following only `docs/quickstart.md`, no constraint vocabulary ever appears, and `make test` plus `make lint` are green.

**Total: ~6.5 engineer-weeks for a single contributor.** Phases 2–5 are individually shippable as `0.4.0-alpha.N` releases.

## 10. Decisions to make before Phase 1

Tracked as questions, not assumed:

1. **Repo split.** Do `agent`, `patterns`, `vector`, and `mesh` move to `skaal-contrib`, or are they deleted and resurrected from git history if/when someone champions them? Recommended: delete + archive branch. Cheaper to maintain.
2. **License.** GPL-3.0 was the right choice when the product was a research-grade constraint solver. For a Python Encore, MIT/Apache-2.0 unblocks the commercial users who are the natural audience. Recommended: relocate license discussion to its own ADR but flag the dependency on it for adoption.
3. **AWS vs GCP first.** Phase 4 cannot ship both in parallel. AWS first (broader user base, existing examples), GCP follows in 0.4.x point release.
4. **Lock file format.** TOML matches the rest of the project's config surface. Alternative (JSON) is rejected — humans edit lock files during migrations.
5. **Backend protocol re-introduction.** v1 has a fixed table. The third-party backend story re-enters in 0.5 via a stable `BackendProtocol`. Not in scope here; just guarantee the binding/registry layout admits it without redesign.

## 11. Non-goals

Explicitly out of scope, to prevent scope creep during implementation:

1. Cost optimization, cost reporting, cost-aware binding. Cost is not the friction.
2. A constraint DSL of any flavor — including "soft" hints. The defaults table absorbs the surface.
3. A web UI. CLI + IDE plugins first. The web UI is a Phase 8+ deliverable, post-v1.
4. Multi-cloud single-app deployments. One environment, one cloud. Per-environment cloud choice is supported (prod=aws, staging=gcp) but the binding within an environment is single-cloud.
5. Agent / actor primitives. They become a v2 concern once code-first inference is undeniably working.

## 12. Success criteria for v0.4.0

The release ships when all of the following are simultaneously true:

1. `skaal init && skaal run` requires zero arguments and zero config edits.
2. `skaal plan --env prod` produces a deterministic diff that a developer can read in under 30 seconds.
3. `skaal deploy --env prod` writes a `skaal.lock` and the next `skaal plan` is empty unless code changed.
4. A `Store[T]` declared in one module is importable, typed, and usable from another module via `from skaal_clients...` with no manual wiring.
5. Opening a PR posts an infra diff comment automatically.
6. The word "constraint" appears nowhere in user-facing docs, CLI help, or decorator signatures.
7. The `examples/todo_api` walkthrough deploys cleanly to AWS in under 5 minutes from a fresh checkout.

When all seven hold, the redesign is done. The product Skaal claims to be — your code is your architecture — is finally the product Skaal is.

## 13. The pitch (canonical)

> **Skaal: your Python app is your architecture.**
> Write classes, functions, and handlers. Skaal infers the infrastructure, generates the Pulumi, and gives you typed clients for every primitive. One codebase. One mental model. `skaal deploy` knows what to build.

This sentence is the contract. Every API decision in this ADR exists to make it literally true.
