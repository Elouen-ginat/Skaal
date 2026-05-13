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

Calling `signup` from another module is typed end-to-end and identical whether running locally or in the cloud — **no generated client package, no separate import path**. The decorated symbol is itself the typed client:

```python
from acme.signup import signup            # the original module path
result: User = await signup(User(id="u1", email="a@b.com"))
#       ^^^^                              # Pylance: result is User
#                ^^^^^^                   # Pylance: signup is FunctionRef[[User], User]
```

Same story for storage primitives — the class **is** the client:

```python
from acme.users import Users
user: User | None = await Users.get("u1")  # Pylance: user is User | None
await Users.put("u1", user)                # Pylance: Users.put takes (str, User)
```

There is no `skaal_clients/` package generated into the source tree. The IDE sees the real types from the real source, instantly, no codegen step in the loop. (For *cross-process* RPC into another Skaal app's source tree, the optional `skaal stubs` command emits a typed `.pyi` stub package — see §6.6 and §6.13.)

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
9. **A single override vocabulary** — typed backend class tokens (`Store[User, Redis]`, `Relational[Sale, BigQuery]`) at declaration sites; the same names as strings only inside `skaal.toml` env overrides. Same words for local override, env-specific override, and global override; LSP follows the class token straight to the backend SDK.

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
  │ Layer 5 — Typed-client surface (NO codegen in dev loop)      │
  │   The primitive classes ARE the typed clients. `Users.get`   │
  │   is typed via `Store[User, B]`; the IDE resolves it from    │
  │   the user's own source. Cross-process RPC uses `skaal       │
  │   stubs` (one-shot .pyi emit). See §6.6, §6.13.              │
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
    # 1. Type-pinning (declaration-site `Relational[Sale, BigQuery]`) is absolute.
    #    Lock entries and env overrides may NOT name a different backend; that is
    #    a `TypePinViolation` raised at config-load time. The env still supplies
    #    per-backend config (project, dataset, region, emulator) via env.backends.
    if res.overrides.backend_token is not None:
        token = res.overrides.backend_token
        if (env.name, res.id) in lock.entries and lock.entries[(env.name, res.id)].backend != token.name:
            raise TypePinViolation(res, lock.entries[(env.name, res.id)].backend)
        if res.id in env.bindings and env.bindings[res.id].backend != token.name:
            raise TypePinViolation(res, env.bindings[res.id].backend)
        return BoundResource(
            inferred=res,
            backend=token.name,
            backend_config=env.backends.get(token.name),   # project/dataset/emulator/etc.
            pinned=True,
        )

    # 2. Lock wins for un-pinned resources.
    if (env.name, res.id) in lock.entries:
        e = lock.entries[(env.name, res.id)]
        return BoundResource(inferred=res, backend=e.backend, region=e.region, pinned=True,
                             backend_config=env.backends.get(e.backend))

    # 3. Env-level override for un-pinned resources.
    if res.id in env.bindings:
        b = env.bindings[res.id]
        return BoundResource(inferred=res, backend=b.backend, region=b.region,
                             backend_config=env.backends.get(b.backend), options=b.options, pinned=False)

    # 4. Defaults table — the only path that produces backend substitution across envs,
    #    and it only applies to un-pinned classes.
    return BoundResource(
        inferred=res,
        backend=DEFAULTS[res.kind][env.profile],
        backend_config=env.backends.get(DEFAULTS[res.kind][env.profile]),
        region=env.region,
        pinned=False,
    )
```

`Environment.backends: dict[str, BackendConfig]` carries the per-backend config block (`project`, `dataset`, `region`, `emulator`, `table_prefix`, …) validated by each backend's `options_schema`. This is the mechanism that lets `env.local` point pinned BigQuery classes at `acme-dev:alice_sandbox` while leaving un-pinned `Store[User]` resources on local SQLite.

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

#### 6.4.2 Their static types (Pylance-discoverable)

The two shapes are typed so that the IDE sees the user's original signature on every call site — there is no opaque wrapper that swallows the parameter and return types.

```python
from typing import Awaitable, Callable, ParamSpec, TypeVar, overload
from skaal.types import FunctionMetadata, AuthMethod

P = ParamSpec("P")
R = TypeVar("R")

class FunctionRef(Generic[P, R]):
    """Returned by @app.function. Statically callable, plus carries metadata."""
    metadata: FunctionMetadata
    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
    async def local(self, *args: P.args, **kwargs: P.kwargs) -> R: ...   # force in-process
    async def remote(self, *args: P.args, **kwargs: P.kwargs) -> R: ...  # force RPC

@overload
def function(fn: Callable[P, Awaitable[R]], /) -> FunctionRef[P, R]: ...
@overload
def function(
    *,
    memory_mb: int | None = None,
    timeout_s: float | None = None,
    min_concurrency: int | None = None,
    max_concurrency: int | None = None,
    auth: AuthMethod | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], FunctionRef[P, R]]: ...
```

For `app.mount`:

```python
from asgiref.typing import ASGIApplication  # standard ASGI 3 protocol

class App:
    def mount(self, path: str, app: ASGIApplication, /) -> None: ...
```

Any FastAPI / Starlette / Litestar instance satisfies `ASGIApplication`; Pylance catches mistakes like passing a sync WSGI app or a plain callable.

### 6.5 The override vocabulary (the entire user-facing tuning surface)

Three knobs. That's the whole API for "I want something other than the default."

1. **Resource-local override** — at the declaration site, using a **typed backend class** (not a string), so Pylance sees it:

   ```python
   from skaal.backends.redis import Redis
   from skaal.backends.bigquery import BigQuery

   class Users(Store[User, Redis]):                    # second generic param == backend
       ...

   class Sales(Relational[Sale, BigQuery]):
       transaction_id: str = Field(primary_key=True)

   @app.function(memory_mb=1024, timeout_s=30)
   async def signup(user: User) -> User: ...
   ```

   When the second generic parameter is omitted (e.g. `Store[User]`), the env profile picks the backend through the defaults table. When it is supplied, the binding is **type-pinned**: the class is statically known to be a Redis-backed `Store`, every method signature on it specialises to Redis capabilities, and the `Users.native()` escape (§6.13) returns the concrete Redis client typed as `redis.asyncio.Redis`. An env override that tries to point a type-pinned class at a different backend fails at config-load time with a typed error.

   String forms (`backend="redis"`) are **not** accepted at declaration sites — strings are opaque to the IDE. They are accepted only inside `skaal.toml` (which is itself a string format) and validated against the registry at load time.

2. **Environment override** — in `skaal.toml`:

   ```toml
   [env.prod]
   profile = "cloud-aws"
   region = "eu-west-1"

   [env.prod.bindings]
   "acme.users:Users"   = "dynamodb"
   "acme.users:Avatars" = { backend = "s3", region = "us-east-1" }
   ```

3. **Per-invocation client overrides (test-time only).** Un-pinned classes accept any compatible backend instance:

   ```python
   from acme.users import Users                    # Store[User] — un-pinned
   from skaal.testing import in_memory
   await Users.bind(in_memory()).put("u1", user)   # OK: un-pinned, anything goes
   ```

   Pinned classes accept *only* an instance of the pinned backend (typically an emulator client). The type system enforces this; the framework refuses anything else at bind time.

   ```python
   from acme.sales import Sales                    # Relational[Sale, BigQuery] — pinned
   from skaal.testing.bigquery import emulator_client
   await Sales.bind(emulator_client("http://localhost:9050")).put("t1", sale)  # OK
   await Sales.bind(in_memory())                                                # TypePinViolation
   ```

   The intended path for tests is configuration (`[env.test.backends.bigquery] emulator = ...`), not per-invocation rebinding. The `.bind()` form exists for rare cases where a single test wants to use a different emulator endpoint than the rest of the suite.

Anything beyond these three knobs is a sign the user is trying to express a constraint, which is the product we just deleted. The defaults table absorbs the rest.

#### 6.5.1 Worked example — `Relational[Sale, BigQuery]` (and how local dev talks to real BigQuery)

The concrete question: "My code is BigQuery-specific. I use native BigQuery SQL, partitioning, and the `bigquery.Client` directly. I want to run locally and have local talk to the deployed dev BigQuery dataset. I do **not** want the framework to substitute SQLite for BigQuery anywhere."

Answer: type-pin the class. **Pinning is a commitment — Skaal will not substitute a different backend for a pinned class in any environment, including `local`.** The framework only mixes backends per env for *un-pinned* classes.

```python
# acme/sales.py
from datetime import datetime
from decimal import Decimal
from google.cloud.bigquery import Client as BQClient
from pydantic import BaseModel
from sqlmodel import Field
from skaal import Relational
from skaal.backends.bigquery import BigQuery        # the typed backend token

class Sale(BaseModel):
    transaction_id: str
    amount: Decimal
    occurred_at: datetime

class Sales(Relational[Sale, BigQuery], partition_by="occurred_at"):
    transaction_id: str = Field(primary_key=True)
    amount: Decimal
    occurred_at: datetime
```

```python
# Anywhere in the codebase — local, dev, prod — this returns a real BigQuery Client.
bq: BQClient = await Sales.native()

job = bq.query(
    f"SELECT DATE_TRUNC(occurred_at, MONTH) AS m, SUM(amount) AS revenue "
    f"FROM `{Sales.qualified_table()}` "
    f"WHERE occurred_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) "
    f"GROUP BY m"
)
for row in job.result():
    ...
```

`Sales.qualified_table()` returns the fully-qualified table name for the active environment (e.g. `acme-dev.alice_sandbox.sales` locally, `acme-prod.acme_warehouse.sales` in prod). The user writes BigQuery SQL with confidence: the dialect is real BigQuery in every environment because the table is real BigQuery in every environment.

Configuration tells Skaal *which* BigQuery instance each environment points at:

```toml
# skaal.toml

[env.local]
profile = "local"               # un-pinned resources (Store[User], etc.) still use local defaults

[env.local.backends.bigquery]   # pinned BigQuery classes talk to this real cloud instance
project = "acme-dev"
dataset = "alice_sandbox"

[env.dev]
profile = "cloud-gcp"
[env.dev.backends.bigquery]
project = "acme-dev"
dataset = "acme_dev_warehouse"

[env.prod]
profile = "cloud-gcp"
[env.prod.backends.bigquery]
project = "acme-prod"
dataset = "acme_warehouse"

[env.test]                       # CI uses the official BigQuery emulator
profile = "local"
[env.test.backends.bigquery]
emulator = "http://localhost:9050"
```

What this gets you:

- `skaal run` (uses `env.local`) connects to real BigQuery in `acme-dev:alice_sandbox`. `Sales.native()` returns a `BQClient` already authenticated and pointed at the sandbox. `Users(Store[User])` (un-pinned) keeps using local SQLite — Skaal does not pull every un-pinned resource into the cloud just because one resource is cloud-pinned.
- `skaal deploy --env prod` provisions in `acme-prod:acme_warehouse`. Same code, same SQL, same client. No dialect surprises.
- `pytest` (with `SKAAL_ENV=test`) routes the BigQuery client at the local emulator — the user is responsible for running the emulator (docker compose, fixture). No mocks; no test-only fakes the framework has to ship.
- An attempt to override `Sales` to a different backend in `skaal.toml` (`"acme.sales:Sales" = "postgres"`) fails at config-load with `TypePinViolation` pointing at the source line where `Relational[Sale, BigQuery]` is declared.

Hover `bq` in VSCode → `(variable) bq: Client`. Autocomplete on `bq.` shows every BigQuery SDK method. No `cast()`, no `Any`, no stringly-typed indirection, no substituted backend.

#### 6.5.2 Kinds, not just names — why BigQuery is not a drop-in for Postgres

`Relational` covers two distinct workload shapes: OLTP (row-level reads/updates, transactions) and analytics (append-mostly, columnar scans). The registry encodes this by tagging each backend with the kinds it *actually* supports:

| Backend | Kinds satisfied |
|---|---|
| `postgres` | `relational-oltp`, `relational-analytics` (modest scale) |
| `cloud-sql-postgres` | `relational-oltp`, `relational-analytics` (modest scale) |
| `sqlite` | `relational-oltp` (single-writer) |
| `bigquery` | `relational-analytics` |
| `redshift` (future) | `relational-analytics` |

A `Relational` class infers its required kinds from its declaration: a `primary_key` plus calls to `.update(...)` or `.delete(...)` in the codebase mark it as `relational-oltp`; append-only with `partition_by=...` and `@app.function` query patterns mark it `relational-analytics`. If the user writes `Relational[Sale, BigQuery]` on a class the inference flagged as OLTP-shaped, import fails with:

```
RelationalKindMismatch: acme.sales:Sales is bound to 'bigquery' which supports
  {relational-analytics}, but the class uses row-level update() at
  acme/sales.py:42. Either remove the row-level mutation or pick a backend
  in {postgres, cloud-sql-postgres}.  See `skaal backends list --kind relational-oltp`.
```

This is the only place the framework gets opinionated about workload semantics. It is deterministic, source-located, and uses the same vocabulary as the rest of the override system.

#### 6.5.3 Pinning is a commitment — no backend substitution, ever

The contract: **a type-pinned class runs on its declared backend in every environment, including `local`. Skaal will never silently substitute a different backend for a pinned class.** The framework only chooses backends for *un-pinned* classes.

| Class shape | Where it runs | `.native()` available? | Substitution allowed? |
|---|---|---|---|
| `Relational[Sale]` (un-pinned) | Backend per env from defaults table or env override (SQLite locally, Postgres in cloud-aws, …) | No — un-pinned classes get only the portable API (`put`, `get`, `scan_page`, `query_index`) | Yes — that's the whole point of leaving the type un-pinned |
| `Relational[Sale, BigQuery]` (pinned) | Real BigQuery in every env; `env.<name>.backends.bigquery` names the project/dataset/emulator | Yes — `Sales.native()` returns `google.cloud.bigquery.Client` | **No.** Env-level override that names a different backend → `TypePinViolation` at config-load |

Concrete consequences:

1. **`skaal run` (local) connects to real cloud for pinned classes.** No SQLite-pretending-to-be-BigQuery. The dev experience matches production because the backend matches production.
2. **The framework mixes per-app.** Un-pinned `Users(Store[User])` keeps using local SQLite; pinned `Sales(Relational[Sale, BigQuery])` uses real BigQuery. You pay the cloud bill exactly where you opted in.
3. **`Sales.qualified_table()`, `Channels.topic_arn()`, `Avatars.bucket_url()`** — every pinned class exposes the active env's resource address as a method, so SQL strings, ARNs, and URIs always resolve to a real, current address. No environment variables to thread, no `os.environ.get("BQ_DATASET", "default")` patterns.
4. **No silent failure mode.** Pylance is statically correct; the runtime is operationally correct. The two never disagree.

For workloads where you genuinely want portable storage and you'll restrict yourself to the portable API, leave the class un-pinned. The framework picks per env, but you give up `.native()` — there is nothing typed for you to escape into, because the typed surface depends on a backend commitment.

#### 6.5.4 Local dev for cloud-pinned backends — credentials, emulators, cost

When a class pins to a cloud backend, `skaal run` makes real cloud calls from the developer's laptop (unless an emulator is configured). Three knobs control how:

1. **Credentials.** Standard cloud SDK auth — Skaal does not manage credentials.
   - GCP: `gcloud auth application-default login`.
   - AWS: AWS CLI / SSO / environment variables / IRSA.
   - The cloud SDK clients pick them up; Skaal stays out of it. `skaal doctor` only verifies the SDK can resolve credentials for each pinned backend.

2. **Per-env backend config.** Each environment names which dataset/table/region the pinned backend should talk to. This is `Environment.backends: dict[str, BackendConfig]`:

   ```toml
   [env.local.backends.bigquery]
   project = "acme-dev"
   dataset = "alice_sandbox"          # per-developer sandbox

   [env.local.backends.dynamodb]
   region = "eu-west-1"
   table_prefix = "alice-"             # per-developer prefix on a shared dev table
   ```

3. **Emulator opt-in.** For unit tests or CI where reaching real cloud APIs isn't acceptable, point the backend at the official emulator. Skaal routes the SDK client there; the user is responsible for running the emulator (docker compose / pytest fixture).

   ```toml
   [env.test.backends.bigquery]
   emulator = "http://localhost:9050"

   [env.test.backends.dynamodb]
   emulator = "http://localhost:8000"

   [env.test.backends.s3]
   emulator = "http://localhost:9000"   # MinIO

   [env.test.backends.firestore]
   emulator = "localhost:8080"
   ```

   Skaal documents which emulators each backend supports; backends without a credible emulator (most managed services) require either a real cloud test resource or the user accepting that those tests are skipped under `env.test`.

Cost and isolation are the user's responsibility. The product principle is "no surprises in production"; the trade-off for honest local dev against a cloud-pinned backend is that you pay for the queries you actually run. The recommended pattern is per-developer sandbox datasets/tables, scoped by `env.local.backends.<name>` in each contributor's local TOML (or `skaal.local.toml`, which is gitignored by default and overlays `skaal.toml`).

### 6.6 The primitive class **is** the typed client (no codegen in the dev loop)

Earlier drafts of this ADR proposed an auto-generated `skaal_clients/` package. That is the **wrong choice for Python**: Pylance and Pyright cannot resolve symbols that don't exist on disk until a build step runs, generated packages cause merge conflicts and stale-state bugs, and Python's import system makes "the class is the client" a far cleaner answer than codegen.

The redesigned model: **every primitive class is itself the typed client.** No generation, no separate import path, no manifest in the dev loop.

| Surface | What the user imports | Why it's already typed |
|---|---|---|
| `Store[T, B]` / `Relational[T, B]` / `BlobStore[B]` / `Channel[T, B]` | The user's own class directly: `from acme.users import Users` | The class is `Generic[T, BackendT]`; method signatures specialise on `T` and `B`. Pylance resolves with zero codegen. |
| `@app.function` callables | The decorated symbol: `from acme.signup import signup` | The decorator returns `FunctionRef[P, R]` typed via `ParamSpec` (§6.4.2); call-site shows the original signature. |
| Backend-native escape (type-pinned classes only) | `await Sales.native()` on `class Sales(Relational[Sale, BigQuery])` | Concrete return type per backend (`google.cloud.bigquery.Client`, `redis.asyncio.Redis`, `asyncpg.Pool`, …). The escape is only defined on pinned classes — un-pinned classes get no `.native()` because there is no statically-known SDK to return. |
| Mounted ASGI services | The user's own FastAPI / Starlette / Litestar app | Skaal does not own this surface. Users keep the client tooling that ships with their routing framework (FastAPI's OpenAPI client gen, etc.). |

What happens at runtime is that `skaal run` and `skaal deploy` wire each declared class to a concrete backend through the binding layer — but at *typing* time, none of that matters: the class hierarchy is fully visible to Pylance from the moment the user finishes typing it.

#### 6.6.1 The one case codegen is justified — cross-process stubs

There is exactly one legitimate codegen path: when **another Python project** wants to call a Skaal app's `@app.function`s by name without importing its source tree. For that, Skaal ships a single command:

```bash
$ skaal stubs --from ./services/billing --to ./apps/web/_stubs --as billing_stubs
```

This emits a typed `.pyi`-only stub package (no runtime code) listing every `@app.function` and `Store[T]` exposed by the source app, validated against a pydantic `StubManifest` model. The consuming project drops the path into `pyrightconfig.json` / `pyproject.toml` and gets full LSP completion against the remote service. Stubs are explicit, opt-in, and live in the consuming project — not in the producing one. Same-process callers never run this command.

This collapses the "always-generated `skaal_clients/`" idea down to: "the class is the client; stubs only exist for crossing a service boundary."

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

A single Python module — `skaal/binding/registry.py` — owns the list of every backend Skaal knows. Each backend is **both a typed class token** (imported and used as the second generic parameter on `Store`/`Relational`/etc.) **and a registry entry** (a pydantic record describing kinds, profiles, capabilities, and the typed native client). The same data structure powers the binder, `skaal backends list`, the import-time validation, and the typed `.native()` escape hatch.

Pinning to a backend token (`Relational[Sale, BigQuery]`) **bypasses the defaults table entirely**: the binder ignores `DEFAULTS[ResourceKind][EnvProfile]` for that resource, refuses any env or lock entry that names a different backend (raising `TypePinViolation`), and uses `env.backends.<token-name>` only to resolve per-env config (project, dataset, region, emulator). The defaults table is the policy for un-pinned resources; pinned resources answer to the type system, not the table.

```python
# skaal/backends/_base.py
from typing import ClassVar, TypeVar, Generic

NativeClientT = TypeVar("NativeClientT")

class Backend(Generic[NativeClientT]):
    """Base for every backend type token. Subclasses are imported at user code sites."""
    name: ClassVar[str]
    kinds: ClassVar[frozenset[str]]
    NativeClient: ClassVar[type[NativeClientT]]

    # The token carries the typed factory; primitive classes call into it via .native().
    @classmethod
    async def _open(cls, config: BackendConfig | None) -> NativeClientT:
        """Construct the SDK client for the active env's config. Framework-internal."""
        ...

# skaal/backends/bigquery/__init__.py
from google.cloud.bigquery import Client as _BQClient
from skaal.backends._base import Backend

class BigQuery(Backend[_BQClient]):
    name = "bigquery"
    kinds = frozenset({"relational-analytics"})
    NativeClient = _BQClient

# skaal/backends/postgres/__init__.py
from asyncpg import Pool as _PgPool
class Postgres(Backend[_PgPool]):
    name = "postgres"
    kinds = frozenset({"relational-oltp", "relational-analytics"})
    NativeClient = _PgPool
```

The registry then captures the operational metadata (profiles, capabilities, options schema) per backend:

```python
class BackendCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ttl: bool = False
    secondary_indexes: bool = False
    transactions: bool = False
    streaming: bool = False
    row_updates: bool = False
    partitioning: bool = False

class BackendEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    token: type[Backend]                 # the typed class (BigQuery, Postgres, Redis, …)
    profiles: frozenset[EnvProfile]
    capabilities: BackendCapabilities
    options_schema: type[BaseModel]      # pydantic schema for backend-specific options

REGISTRY: tuple[BackendEntry, ...] = (
    BackendEntry(token=Postgres,  profiles={LOCAL, CLOUD_AWS}, …),
    BackendEntry(token=BigQuery,  profiles={CLOUD_GCP},        …),
    BackendEntry(token=Redis,     profiles={LOCAL, CLOUD_AWS}, …),
    BackendEntry(token=DynamoDB,  profiles={CLOUD_AWS},        …),
    BackendEntry(token=Firestore, profiles={CLOUD_GCP},        …),
    BackendEntry(token=S3,        profiles={CLOUD_AWS},        …),
    # …
)
```

Rules the registry enforces (all at import time, all with source-located errors):

1. Every typed binding (`Store[T, B]`, `Relational[T, B]`, …) requires `B` to be a registered `Backend` subclass. Unknown class → `UnknownBackendError` listing valid alternatives.
2. The chosen entry's `token.kinds` must include every kind the inferred resource requires (§6.5.2). Otherwise → `BackendKindMismatch` with the offending source line.
3. The entry must include the active `Environment.profile` in `profiles`. Otherwise → `BackendNotAvailableInProfile`.
4. Backend-specific options (`partition_by=`, `dataset=`, …) are validated against `options_schema`. No untyped option dicts cross the binding boundary.
5. Env-level string overrides in `skaal.toml` are looked up by `token.name` and validated against the same rules at config-load time.

The registry is a static module. Adding a new backend is one PR that adds a `Backend` subclass, one `BackendEntry`, and one test. There is no entry-point discovery, no TOML catalog overlay, no per-environment plugin set. Third-party backends re-enter in a later version through a documented `BackendProtocol` plus a registration call; the registry's data shape is already designed to admit them.

### 6.13 Static typing and LSP discoverability (the binding contract)

This section is the framework's typing contract. Every public API listed in §8 must satisfy it. CI enforces it via Pyright in strict mode against the example apps; the success criteria in §12 include an explicit LSP-discoverability check.

#### 6.13.1 Generic shapes

Every storage-like primitive carries two type parameters: the payload model and (optionally) the backend token. Both are visible to Pylance:

```python
from typing import Generic, TypeVar
from typing_extensions import TypeVar as TypeVarExt        # PEP 696 default= on 3.11

T = TypeVar("T", bound=BaseModel)
B = TypeVarExt("B", bound=Backend, default=Backend)        # default = generic backend

class Store(Generic[T, B]):
    @classmethod
    async def get(cls, key: str) -> T | None: ...
    @classmethod
    async def put(cls, key: str, value: T) -> None: ...
    @classmethod
    async def native(cls) -> B.NativeClient: ...           # typed escape

class Relational(Generic[T, B]): ...
class BlobStore(Generic[B]): ...
class Channel(Generic[T, B]): ...
```

Resulting Pylance experience:

| User code | Pylance reveals |
|---|---|
| `class Users(Store[User, Redis]): ...` | `Users` is `type[Store[User, Redis]]` |
| `await Users.get("u1")` | `User \| None` |
| `await Users.put("u1", x)` | requires `x: User`; passing a `dict` errors |
| `await Users.native()` | `redis.asyncio.Redis` |
| `class Avatars(BlobStore[S3]): ...` then `await Avatars.native()` | `aioboto3.S3.Client` |
| `class Sales(Relational[Sale, BigQuery]): ...` then `await Sales.native()` | `google.cloud.bigquery.Client` |
| `class Plain(Store[User]): ...` then `Plain.native` | **does not exist** — un-pinned class has no `.native()` member. Pylance reports `Cannot access member "native"`. To get a native client you must pin the type. |

#### 6.13.2 The three idiomatic patterns

```python
# 1. Un-pinned, portable.  The framework chooses the backend per env from the
#    defaults table.  You commit to using only the portable API; no .native().
class Users(Store[User]):
    ...
user = await Users.get("u1")                     # Pylance: User | None
# await Users.native()  -> Pylance error: "Cannot access member 'native'"

# 2. Type-pinned, IDE-typed native escape.  The same backend runs in every env
#    (local talks to a real cloud instance per env.<name>.backends.<token> config).
#    Use this for backend-specific code (BigQuery SQL, Redis Lua, DynamoDB PartiQL).
from skaal.backends.bigquery import BigQuery
class Sales(Relational[Sale, BigQuery], partition_by="occurred_at"):
    ...
bq: bigquery.Client = await Sales.native()       # real BigQuery client in every env

# 3. Decorated function.  Auto-RPC; signature is preserved at call sites.
@app.function
async def signup(user: User) -> User:
    ...
result: User = await signup(User(...))           # Pylance shows (user: User) -> User
```

#### 6.13.3 Discoverability properties (each one tested)

| Property | Test |
|---|---|
| No `Any` leaks from public API | `pyright --strict skaal/ examples/` reports zero implicit-`Any` warnings on any imported symbol. |
| Decorator preserves signatures | After `signup = app.function(signup)`, `reveal_type(signup)` is `FunctionRef[[User], User]`, and `await signup(user)` reveals `User`. |
| Pinned class gives concrete native client | After `class Cache(Store[V, Redis])`, `reveal_type(await Cache.native())` is `redis.asyncio.Redis`. |
| Un-pinned class has no `.native()` | After `class Plain(Store[User])`, `Plain.native` triggers Pyright `reportAttributeAccessIssue`. |
| Pinning bypasses substitution | `class Sales(Relational[Sale, BigQuery])` plus `[env.local.bindings] "...Sales" = "postgres"` raises `TypePinViolation` at config-load (no runtime substitution path exists). |
| Local dev talks to real cloud for pinned classes | With `[env.local.backends.bigquery] project = "..."` set, `await Sales.native()` returns a `google.cloud.bigquery.Client` authenticated against the named project; the SQLite default for `RELATIONAL` is never reached. |
| Kind mismatches are reported at import time | `class Sales(Relational[Sale, BigQuery])` plus a call to `Sales.update(...)` errors out at import with `BackendKindMismatch`. |
| ASGI mount is type-checked | `app.mount("/api", 42)` fails Pyright; `app.mount("/api", FastAPI())` passes. |
| Pydantic surfaces round-trip through `model_validate_json` | `InferredPlan.model_validate_json(plan.model_dump_json()) == plan` in tests. |
| No string-typed backend at declaration sites | `grep -RE 'backend\s*=\s*"' skaal/ examples/` returns zero hits. Strings appear only in `skaal.toml`. |
| Generated stubs (when used) declare `py.typed` | `skaal stubs` always emits a `py.typed` marker and `*.pyi` files; the package is a `partial-stub` per PEP 561. |

#### 6.13.4 Why this is enforceable

Three design choices keep the above LSP-trivial and runtime-honest rather than requiring HKT gymnastics or trust:

1. **`.native()` only exists on type-pinned primitives.** When `B` is the default `Backend`, the framework does not define `.native()` on that class at all — Pyright reports the missing member, the IDE refuses the call, and there is no "best-effort" runtime that would silently return the wrong client. Pinning to a concrete `B` enables the method, and the return type is `B.NativeClient`, which Pyright resolves via the standard `Generic[NativeClientT]` mechanism on the `Backend` base class.
2. **Class tokens, not strings, at every declaration site.** A token is a real Python class — its import is resolvable, its identity is checkable, and it's discoverable by the IDE's autocomplete. A string is none of those.
3. **No substitution path for pinned classes.** The binder *cannot* return a different backend than the one in the type, because the only branch that consults the defaults table is gated on `res.overrides.backend_token is None` (§6.3). The same pin that gives the IDE its types gives the runtime its truth.

Together they give a framework whose entire public surface is navigable from a single `Go to Definition` chain, starting from the user's own class declaration and ending at the underlying SDK client — and where the type the IDE shows you is the type the runtime actually uses, in every environment.

## 7. The new CLI

Trimmed to what fits the thesis. Each verb has one clear job.

| Verb | Purpose |
|---|---|
| `skaal init` | Scaffold a new project. Writes `skaal.toml` with one env (`local`) and a starter `app.py`. |
| `skaal run` | Start the local runtime. Hot reload by default in TTY. No client codegen (the primitive classes are the clients; see §6.6). |
| `skaal map` | Print the source → resource tree for an environment. |
| `skaal plan [--env <name>] [--against=deployed]` | Print the structural or state diff. |
| `skaal deploy --env <name>` | Provision via Pulumi. Updates `skaal.lock`. |
| `skaal build --env <name>` | Emit artifacts (Pulumi program, Dockerfiles, handler entrypoints) without provisioning. |
| `skaal rebind --env <name> <resource> <backend>` | Move a pinned binding. Generates migration steps. |
| `skaal unbind --env <name> <resource>` | Remove a pinned binding (resource is being deleted). |
| `skaal where <resource> [--env <name>]` | Open the cloud-console URL for a deployed resource. |
| `skaal trace <log-or-resource>` | Print the source location for a deployed resource or log line. |
| `skaal backends list [--kind <k>] [--profile <p>]` | Print every backend the registry knows, with its `Backend` token import path, supported kinds, and profiles. Discovery surface for typed declaration-site bindings. |
| `skaal stubs --from <src-app> --to <out-dir> [--as <pkg>]` | Emit a typed `.pyi`-only stub package for cross-process callers (PEP 561 `partial-stub` with `py.typed`). Idempotent; no runtime code generated. |
| `skaal doctor` | Sanity-check toolchain (pulumi, docker, cloud credentials, pyright version). |

Removed verbs: `skaal catalog *`, `skaal solver *`, `skaal explain` (folded into `skaal plan --explain`).

## 8. New public API surface (canonical)

`skaal/__init__.py` `__all__` shrinks materially. The keep list, with the typed generic shapes:

```python
# Composition
App, Module, ModuleExport

# Typed primitives (all Generic, second param is the Backend token)
Store[T, B = Backend], Relational[T, B = Backend],
BlobStore[B = Backend], Channel[T, B = Backend]

# Typed callable
FunctionRef[P, R],              # returned by @app.function
function,                       # the single callable primitive (typed via ParamSpec + overload)

# Schedules / jobs
Cron, Every, Schedule, ScheduleContext
JobSpec, JobHandle, JobResult, JobStatus

# Secrets (typed payload)
Secret[T], SecretRegistry

# Value types (all pydantic)
Duration, TTL, Retention, Page[T], SecondaryIndex
InvokeContext, BeforeInvoke,
RetryPolicy, RateLimitPolicy, CircuitBreaker, Bulkhead

# Backend tokens — imported from skaal.backends.<name>
Backend[NativeClientT],         # base; user code rarely references directly
# concrete tokens live in skaal.backends.<name> and are imported there:
#   from skaal.backends.bigquery import BigQuery
#   from skaal.backends.postgres import Postgres
#   from skaal.backends.redis    import Redis
#   from skaal.backends.dynamodb import DynamoDB
#   from skaal.backends.firestore import Firestore
#   from skaal.backends.s3       import S3
#   from skaal.backends.gcs      import GCS
#   ...

# Registry-introspection (read-only)
BackendEntry, BackendCapabilities

# Adapters for user-owned external resources
external, external_channel

# Relational helpers
ensure_relational_schema, open_relational_session

# Sync escape
sync_run
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
3. Type the public surface per §6.13: `Store[T, B]`, `Relational[T, B]`, `BlobStore[B]`, `Channel[T, B]` with `B` defaulted via `typing_extensions.TypeVar(default=Backend)`; `@app.function` decorator with `ParamSpec`/`TypeVar` overloads returning `FunctionRef[P, R]`; `App.mount(path: str, app: ASGIApplication)`.
4. Add `tests/inference/test_fingerprint.py` asserting byte-stability across reorderings, and `tests/inference/test_pydantic.py` asserting every public inference type round-trips through `model_dump_json` / `model_validate_json`.

Exit criterion: `App.infer() -> InferredPlan` returns a complete plan for every example under `examples/`; `InferredPlan.model_json_schema()` is published as the contract artifact; `pyright --strict skaal/` is green.

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

### Phase 5 — Typing contract and cross-process stubs (1 week)

There is no in-tree generated client package — primitive classes are the typed clients (§6.6, §6.13). This phase enforces the LSP contract and ships the one cross-process tool that genuinely needs codegen.

1. Add `pyright --strict` to CI against `skaal/`, `examples/`, and `tests/typing/`.
2. New package `tests/typing/`:
   - `test_reveal_types.py` — `reveal_type` assertions for every row of the §6.13.3 table.
   - `test_no_any_leaks.py` — fails if any public symbol resolves to `Any` from a fresh import.
   - `test_no_string_backend.py` — `grep` gate; rejects any declaration-site string backend.
3. New package `skaal/stubs/`:
   - `emit.py` — walks an external Skaal app's `InferredPlan` and emits a `.pyi`-only PEP 561 `partial-stub` package with a `py.typed` marker.
   - `manifest.py` — pydantic `StubManifest` validated on both ends.
   - CLI verb `skaal stubs --from <src> --to <out> [--as <pkg>]`.
4. Ship a Pyright plugin config (`pyrightconfig.json` snippet) in the docs showing consuming projects how to register the stubs directory.

Exit criterion: in `examples/todo_api`, hovering over `Todos.put` in VSCode shows the typed signature without any codegen having run; `pyright --strict` is green on the whole tree; `skaal stubs` emits a `.pyi` package that, when added to a separate project's `pyrightconfig.json`, gives full LSP completion for `Todos` and every `@app.function`.

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
3. **Backend substitution for type-pinned classes.** A class declared `Relational[Sale, BigQuery]` runs on BigQuery in every environment, including `local`. Skaal will not ship a "local fallback" that runs the same code on SQLite, nor an abstraction layer that pretends one backend's API is another's. Pinning is the user's explicit opt-out from the substitution model; the framework respects it without exception. If a developer wants portable storage, they use the un-pinned form (`Relational[Sale]`) and accept the corresponding loss of `.native()`.
4. **Cross-backend portability shims.** No "BigQuery dialect translator" for Postgres, no DynamoDB-to-Firestore adapter, no `.update()` polyfill on append-only stores. The portable API on un-pinned classes is intentionally a narrow common-denominator surface; native semantics are only available through pinning.
5. A web UI. CLI + IDE plugins first. The web UI is a Phase 8+ deliverable, post-v1.
6. Multi-cloud single-app deployments. One environment, one cloud. Per-environment cloud choice is supported (prod=aws, staging=gcp) but the binding within an environment is single-cloud.
7. Agent / actor primitives. They become a v2 concern once code-first inference is undeniably working.

## 12. Success criteria for v0.4.0

The release ships when all of the following are simultaneously true:

1. `skaal init && skaal run` requires zero arguments and zero config edits.
2. `skaal plan --env prod` produces a deterministic diff that a developer can read in under 30 seconds.
3. `skaal deploy --env prod` writes a `skaal.lock` and the next `skaal plan` is empty unless code changed.
4. A `Store[T]` declared in one module is importable, typed, and usable from another module via direct Python import (`from acme.users import Users`) with no codegen step and no `skaal_clients/` package in the source tree.
5. `pyright --strict` is green on `skaal/`, `examples/`, and `tests/typing/`; `reveal_type` assertions for every row of §6.13.3 pass; hovering over any primitive method in VSCode shows the typed signature without running a build step.
6. `class Sales(Relational[Sale, BigQuery])` plus `bq = await Sales.native()` resolves `bq` to `google.cloud.bigquery.Client` in Pylance; `skaal run` against `[env.local.backends.bigquery] project = "acme-dev"` connects to that real cloud dataset (no substitution); attempting to override `Sales` to a different backend via `skaal.toml` fails at config-load with `TypePinViolation`.
7. Opening a PR posts an infra diff comment automatically.
8. The word "constraint" appears nowhere in user-facing docs, CLI help, or decorator signatures.
9. The `examples/todo_api` walkthrough deploys cleanly to AWS in under 5 minutes from a fresh checkout.

When all nine hold, the redesign is done. The product Skaal claims to be — your code is your architecture, fully typed and discoverable in your IDE — is finally the product Skaal is.

## 13. The pitch (canonical)

> **Skaal: your Python app is your architecture.**
> Write classes and functions. Skaal infers the infrastructure, generates the Pulumi, and your primitive classes are the typed clients. `Pylance` follows every call site straight down to the underlying SDK. One codebase. One mental model. `skaal deploy` knows what to build.

This sentence is the contract. Every API decision in this ADR exists to make it literally true.
