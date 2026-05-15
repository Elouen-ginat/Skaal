# ADR 032 — Runtime/Deploy on `BoundPlan` Implementation Plan (Phase 4)

**Status:** Proposed
**Date:** 2026-05-14
**Related:** [ADR 028](028-code-first-infra-redesign.md) (the redesign), [ADR 029](029-redesign-foundation-implementation-plan.md) (Phases 0–1), [ADR 030](030-inference-layer-implementation-plan.md) (Phase 2), [ADR 031](031-binding-layer-implementation-plan.md) (Phase 3)
**Supersedes execution detail in:** ADR 028 §9 Phase 4

---

## Goal

Land Phase 4 of the [ADR 028](028-code-first-infra-redesign.md) redesign: the runtime that *runs* a `BoundPlan` locally, the deploy layer that *generates* Pulumi programs from a `BoundPlan`, and the decorator rewire that puts the typed `Backend` tokens (Phase 3) into user code as the second generic parameter on every primitive.

After Phase 4, `skaal run` and `skaal deploy --env prod` are both wired end-to-end through the new pipeline:

```
App declaration ──▶ infer (Phase 2) ──▶ InferredPlan
                                            │
                              env + lock ──▶▼ bind (Phase 3)
                                          BoundPlan
                                            │
                          ┌─────────────────┼─────────────────┐
                          ▼                                   ▼
                    runtime/local                       deploy/aws (Phase 4)
                  (uvicorn + asyncio)                 (Pulumi Automation API)
```

Every legacy `__skaal_storage__` / `__skaal_function__` / `__skaal_schedule__` / `__skaal_channel__` / `__skaal_job__` dunder is deleted in this phase. After Phase 4 there is one inference contract on user-decorated objects (`__skaal_inferred__`) and one bound contract for runtime/deploy consumers (`BoundPlan`).

## Scope

In scope:

- A new `skaal.runtime` package, rebuilt from scratch on `BoundPlan`. Local execution of every `ResourceKind` against the backends a `local` `Environment` binds to (`Sqlite`, `Redis`, `FilesystemBlob`, `InProcessChannel`, `Uvicorn`, `Apscheduler`, `Asyncio`, `DotenvSecret`).
- A new `skaal.deploy` package generating Pulumi programs from a `BoundPlan`. AWS-first per ADR 028 §10.3; GCP scheduled for a 0.4.x point release.
- The Jinja2 template tree under `skaal/deploy/templates/{aws,local}/` covering one file per Pulumi resource the AWS-first matrix needs.
- Decorator rewire: `Store[T, B]` / `Relational[B]` / `BlobStore[B]` / `Channel[T, B]` backend generic parameter populating `ResourceOverrides.backend` on `__skaal_inferred__` — the second generic on `Store` / `BlobStore` / `Channel`, the only generic on `Relational`.
- `@app.external` decorator using `Environment.backends[name]` as the "user-supplied connection" handle.
- `App.mount(path: str, asgi_app: ASGIApplication)` signature reshape; deletion of `mount_asgi` / `mount_wsgi` aliases.
- `FunctionRef[P, R]` typed return shape on `@app.function` so call-site invocations type-check across module boundaries.
- Per-backend public import re-export modules (`from skaal.backends.redis import Redis`) thin shims around `skaal.backends._tokens`.
- Resource tagging on every cloud resource (`skaal:app`, `skaal:resource_id`, `skaal:env`, `skaal:fingerprint`) per ADR 028 §6.11.
- Deletion of every legacy `__skaal_*__` dunder mentioned in ADR 030 Decision 2 (and the predicates that read them in `skaal.relational`, `skaal.blob`, `skaal.schedule`, `skaal.storage`).
- Re-activation of `skaal run`, `skaal build`, and `skaal deploy` CLI verbs against the new pipeline. The current stubs go away.
- Tests under `tests/runtime/`, `tests/deploy/`, and `tests/decorators/` covering each new contract.

Out of scope (each lands in its own phase/ADR):

- **GCP deploy targets.** Phase 4 ships AWS-first per ADR 028 §10.3. The Jinja2 template tree is laid out so `skaal/deploy/templates/gcp/` is a drop-in addition, but `Pubsub` / `CloudRun` / `CloudSchedulerCloudRun` / `CloudTasksCloudRun` / `Firestore` / `Gcs` / `GcpSecretManager` Pulumi programs are not in this phase. A 0.4.x point release closes the gap.
- **`pyright --strict skaal/`.** Phase 5 (ADR 033) owns the global strict-typing pass. Phase 4 brings its own contribution (`skaal.runtime.*` and `skaal.deploy.*` strict at construction) but does not block the wider tree on it.
- **Cross-process typed stubs (`skaal stubs`).** ADR 033 / Phase 5.
- **`skaal plan` diff against `LockFile` or live state.** ADR 034 / Phase 6 owns the diff renderer; Phase 4's `skaal plan` prints the `BoundPlan` in a human-readable form (the diff is left for Phase 6).
- **`relational-oltp` / `relational-analytics` kind refinement.** ADR 028 §6.5.2 calls for the bytecode-level call-graph walker that disambiguates the two; that lands in Phase 6 alongside the `map` / `where` / `trace` work. Phase 4 emits a single `RELATIONAL` kind, bound to whichever Postgres flavour the AWS deploy template picks (`RdsPostgres`).
- **Third-party `BackendProtocol`.** ADR 028 §10.5 defers this to v0.5.
- **Pulumi state backend selection (S3, GCS, local).** Phase 4 hard-codes Pulumi to use the user's existing Pulumi config (`PULUMI_BACKEND_URL` or `~/.pulumi/`). Migration of state between backends is a v0.5 concern.

## Decision 1 — `BoundPlan` is the one input to runtime and deploy

Every entry point in `skaal.runtime` and `skaal.deploy` accepts a `BoundPlan` and nothing else. The pipeline from declaration to artefact is:

```python
plan = app.infer()                                          # Phase 2
env = load_environment(name, path=Path("skaal.toml"))      # Phase 3
lock = load_lock(Path("skaal.lock"))                       # Phase 3
bound = bind(plan, env, lock)                              # Phase 3
runtime = LocalRuntime.from_bound_plan(bound, app)         # Phase 4 — this ADR
program = pulumi_program_for(bound, app, env)              # Phase 4 — this ADR
```

The `BoundPlan` carries every backend choice the runtime or deploy code needs. Neither layer reads `__skaal_inferred__` directly — they read `BoundResource.backend` and dispatch on the registered `BackendEntry` from `skaal.binding.registry`. The `app` reference is passed alongside `bound` only so the runtime can resolve `BoundResource.id` back to the live Python object (the user's `Store` subclass, the user's `@app.function` callable, …).

This is what justifies the legacy-dunder deletion: once `BoundPlan.resources` is the addressing scheme, no consumer in `skaal/` has any reason to walk `cls.__skaal_storage__` or `fn.__skaal_function__`. The inference dunder (`__skaal_inferred__`) survives because it is the input to `infer(app)`; everything else goes.

## Decision 2 — `Backend` tokens flow into user code via a class-level marker

The backend generic parameter on each primitive (`Store[T, B]` / `Relational[B]` / `BlobStore[B]` / `Channel[T, B]`) is wired by the decorator, not by the metaclass. ADR 028 §6.6 spelled out the intent; the mechanism is:

```python
# Phase 4 — skaal/storage.py
B = TypeVar("B", bound=Backend, default=Backend)

class Store(Generic[T, B]):
    """Typed key-value store. Second generic is the optional backend pin."""
```

The decorator reads `cls.__orig_bases__` (or `typing.get_type_hints(cls)` for `__class_getitem__`-flavoured forms) and, if the second parameter resolves to a registered `Backend` subclass other than `Backend` itself, sets `__skaal_inferred__.overrides.backend = token.name`. The binder (Phase 3) already validates that path; the only new code is the decorator reading the second arg.

`Backend` itself is the default to keep the un-pinned form unchanged — `Store[User]` is still legal because `B` defaults to `Backend`, which carries no `name` and therefore does not populate `ResourceOverrides.backend`. Pylance sees the second parameter on every class but the user never has to type it.

Rationale for the default-defaulting:

1. **No new syntax to learn.** `Store[User]` keeps working in every example without edits.
2. **The default is the "we'll pick" signal.** Phase 3's defaults-table branch covers it without a backend.
3. **The pinned form is a one-token edit.** `Store[User, Redis]` is the natural extension once the user wants a pin.

`PEP 696` defaults are stdlib in Python 3.13 and available via `typing_extensions` on 3.11/3.12. `typing_extensions` is already a transitive dependency through pydantic; the import is unconditional.

## Decision 3 — Local runtime is a `Starlette` ASGI app over `BoundResource`-backed adapters

`skaal.runtime.local` builds a single Starlette `Router` from `BoundPlan.resources`:

| `BoundResource.kind` | Mount point | Adapter |
|---|---|---|
| `STORE` | (no route) | `LocalStoreAdapter` wires `Sqlite` / `Redis` clients to `Store.get/set/list/...` |
| `RELATIONAL` | (no route) | `LocalRelationalAdapter` wires SQLModel sessions backed by `aiosqlite` / `asyncpg` |
| `BLOB` | (no route) | `LocalBlobAdapter` wires `fsspec` (`file://` / `s3://` / `gs://`) |
| `CHANNEL` | (no route) | `LocalChannelAdapter` wires `InProcessChannel` (asyncio queue) or `RedisChannel` |
| `FUNCTION` | `/<resource_id>` (POST) | `LocalFunctionAdapter` invokes the user callable inside the asyncio loop, applies retry/circuit-breaker middleware |
| `SCHEDULE` | (no route) | `LocalScheduleAdapter` registers the callable with the in-process APScheduler |
| `JOB` | `/_jobs/<resource_id>/enqueue` (POST) | `LocalJobAdapter` posts to an asyncio queue consumed by a worker task per job |
| `ASGI_SERVICE` | `/` (mounted) | `LocalASGIAdapter` mounts the user's ASGI app under the configured path |
| `SECRET` | (no route) | `LocalSecretAdapter` reads `.env` via `DotenvSecret` |

Every adapter is a 50–100 line module that takes a `BoundResource` and a live Python object (the `Store` class, the `@app.function` callable, …) and registers it with the `LocalRuntime` instance. There is no abstract `Adapter` base — adapters are duck-typed; the runtime calls `adapter.register(...)` and that's the entire interface.

The adapter dispatch table lives in `skaal/runtime/dispatch.py`:

```python
_LOCAL_DISPATCH: Mapping[ResourceKind, Callable[[BoundResource, Any, App], None]] = {
    ResourceKind.STORE: LocalStoreAdapter.register,
    ResourceKind.RELATIONAL: LocalRelationalAdapter.register,
    ResourceKind.BLOB: LocalBlobAdapter.register,
    ResourceKind.CHANNEL: LocalChannelAdapter.register,
    ResourceKind.FUNCTION: LocalFunctionAdapter.register,
    ResourceKind.SCHEDULE: LocalScheduleAdapter.register,
    ResourceKind.JOB: LocalJobAdapter.register,
    ResourceKind.ASGI_SERVICE: LocalASGIAdapter.register,
    ResourceKind.SECRET: LocalSecretAdapter.register,
}
```

The runtime entry point is `LocalRuntime.serve(host, port)`. It builds the Starlette app, registers every resource, starts the APScheduler, and `uvicorn.run`s the result. `Ctrl-C` triggers `LocalRuntime.shutdown()` which closes connection pools, cancels the worker tasks, and shuts the scheduler down.

The runtime does *not* validate `BoundPlan` shape — Phase 3's `bind()` already validated. The runtime treats `BoundPlan` as a trusted upstream contract.

## Decision 4 — Deploy is one Pulumi-Automation-API program per target, fed by Jinja2 templates

`skaal.deploy.aws.AwsProgram` is the AWS-first deploy entry point. Its `pulumi_program()` method returns a callable Pulumi expects (no decorators, no inline-config magic). The callable walks `BoundPlan.resources` and instantiates one Pulumi resource per `BoundResource`, dispatching by `BoundResource.backend`:

| Backend | Pulumi resources |
|---|---|
| `DynamoDB` | `aws.dynamodb.Table` |
| `Postgres` | `aws.rds.Instance` + `aws.rds.SubnetGroup` |
| `Redis` | `aws.elasticache.ReplicationGroup` |
| `S3` | `aws.s3.BucketV2` + lifecycle |
| `Lambda` | `aws.lambda_.Function` + IAM + log group + (per kind) `aws.apigatewayv2.*` / `aws.events.Rule` / `aws.sqs.Queue` |
| `ApigwLambda` | `aws.apigatewayv2.Api` + `aws.lambda_.Function` |
| `SqsLambdaWorker` | `aws.sqs.Queue` + `aws.lambda_.Function` + event-source-mapping |
| `EventBridgeLambda` | `aws.events.Rule` + `aws.lambda_.Function` + permission |
| `AwsSecretsManager` | `aws.secretsmanager.Secret` |

Each row is one `skaal/deploy/aws/<backend>.py` module exporting a `synthesize(bound, app, env) -> list[pulumi.Resource]` function. The deploy entry point composes them in dependency order (storage before function before route before scheduler).

The Jinja2 template tree under `skaal/deploy/templates/aws/` renders the non-Pulumi artefacts the Lambda runtime needs:

- `Dockerfile` — Python 3.11 slim, `pip install` of the user's project, the Lambda runtime adapter.
- `handler.py` — the per-Lambda entry point that maps event payloads to `@app.function` invocations.
- `requirements.txt` — generated from `pyproject.toml` plus skaal core deps.
- `bootstrap.py` — boot-time setup (logging, secret hydration, backend client warm-up).

The templates are read at code-gen time, not at Pulumi runtime — the rendered artefacts are written to `./.skaal/build/<env>/` and the Pulumi `Function` resource points at that path. The Pulumi program does not template anything inside its own callable, which keeps the Pulumi-Automation-API stack idempotent.

Phase 4 deletes the Phase 1 `skaal/cli/build_cmd.py` stub and replaces it with a real `build` verb that runs the templating pass *without* invoking Pulumi. `deploy` is `build` followed by `pulumi up`. `plan` is `build` followed by `pulumi preview`, with the preview output post-processed into a human-readable summary.

## Decision 5 — Resource tagging is enforced by a single `tags_for(resource, env)` helper

Every cloud resource produced by `skaal.deploy.aws.*` is tagged through one helper:

```python
def tags_for(resource: BoundResource, env: Environment, fingerprint: str) -> Mapping[str, str]:
    return {
        "skaal:app": resource.id.split(":")[0].split(".")[0],
        "skaal:resource_id": resource.id,
        "skaal:kind": resource.kind.value,
        "skaal:env": env.name,
        "skaal:target": env.target.value,
        "skaal:backend": resource.backend,
        "skaal:fingerprint": fingerprint,
    }
```

The `fingerprint` is `InferredPlan.fingerprint` carried through to `BoundPlan.app_fingerprint` (a new field added in this phase — see Implementation §4.3). Every Pulumi resource synth function consumes `tags_for(...)` and passes it to its `tags` argument. The test suite asserts the tag set on a freshly-deployed sample app.

Why a helper not a decorator: Pulumi resource constructors take `tags` as a kwarg; a decorator would force every synth function to a particular signature shape. The helper composes cleanly with `**tags_for(...)` at call sites.

## Decision 6 — `@app.external` reads `Environment.backends[name]` and exposes the typed client

`@app.external` is the user-facing surface for "this resource is provisioned outside Skaal; here is the connection". Its decorator form is:

```python
@app.external(name="legacy_db")
class LegacyDb(Relational[Postgres], table=True):
    id: int | None = Field(default=None, primary_key=True)
    body: str
```

The decorator marks the resource as external on `__skaal_inferred__.overrides.external = True`. The binder (Phase 3) already treats `overrides.backend` as a type-pin; the new `external` flag tells the deploy layer "do not provision; skip codegen for this resource and read the connection from `env.backends[name]` at runtime". The runtime adapter reads `env.backends["legacy_db"].options` for the connection string.

Validation:

1. `@app.external` requires a `name=` kwarg (it indexes into `Environment.backends`).
2. The class must declare a type-pinned second generic (`Postgres`, `Redis`, etc.) — un-pinned `external` is rejected at decoration with `SkaalConfigError`. The deploy layer cannot honour "external something" without knowing the wire protocol.
3. The binder skips defaults / lock / env-override branches for external resources and emits `BoundResource(backend=token.name, pinned=True, external=True)`. `BoundResource` grows a new `external: bool` field for this purpose.

The deploy layer's synth functions check `bound.external` and emit zero Pulumi resources for externals — just a config secret (if `env.backends[name].secret_ref` is set) that wires the connection string at Lambda boot.

## Decision 7 — `App.mount(path, asgi_app)` is the canonical ASGI surface

ADR 028 §6.4.1 calls for `App.mount(path: str, asgi_app: ASGIApplication)` as the canonical form. The Phase 1 / Phase 2 forms (`mount_asgi(asgi_app, attribute="...")`, `mount_wsgi(wsgi_app, attribute="...")`) are replaced. Phase 4:

1. Adds `App.mount(path: str, asgi_app: ASGIApplication) -> None`.
2. Deletes `mount_asgi` / `mount_wsgi`. WSGI users wrap with `asgiref.WSGIMiddleware` at the call site.
3. Updates the `asgi.py` recogniser in `skaal.inference` to read `App._mounts: dict[str, ASGIApplication]` instead of `app._asgi_app`. A separate `ASGI_SERVICE` resource is emitted per mount path.
4. The runtime's `LocalASGIAdapter` mounts each entry into the Starlette router. The deploy layer's API Gateway synth maps each path to a route on the same Lambda function (Phase 4 ships single-Lambda-per-ASGI; Phase 6+ may split).

The signature change is breaking; examples and docs are updated in the same PR. Users on `0.4.0-alpha.2`/`alpha.3` are warned in the alpha release notes.

## Decision 8 — `FunctionRef[P, R]` is `@app.function`'s typed return

`@app.function` currently returns the underlying callable, which means cross-module call sites lose retry/circuit-breaker metadata at the type level. Phase 4 wraps the callable in a `FunctionRef[P, R]`:

```python
# skaal/decorators.py
class FunctionRef(Generic[P, R]):
    """Typed handle to a `@app.function`-decorated callable."""
    __wrapped__: Callable[P, Awaitable[R]]
    id: str
    overrides: ResourceOverrides

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[R]:
        return self.__wrapped__(*args, **kwargs)
```

The decorator returns a `FunctionRef[P, R]` constructed from the original callable's signature; Pylance sees the typed signature on every call site, and the runtime/deploy layers read `.id` / `.overrides` off the ref without `getattr`-tunnelling through `__skaal_*`. The `__call__` indirection keeps `await Greet("Alice")` working unchanged.

`ParamSpec` and the corresponding `Awaitable` overload-on-sync support is Python 3.10+; the codebase's 3.11 floor (see `pyproject.toml`) covers it.

## Implementation

### 4.1 — `skaal/runtime/` rebuild

Layout:

```
skaal/runtime/
├── __init__.py             # re-exports LocalRuntime, serve()
├── local.py                # LocalRuntime class + .from_bound_plan + .serve / .shutdown
├── dispatch.py             # _LOCAL_DISPATCH mapping
├── middleware.py           # retry / circuit-breaker / rate-limit / bulkhead wrappers
├── adapters/
│   ├── __init__.py
│   ├── store.py            # LocalStoreAdapter (Sqlite + Redis)
│   ├── relational.py       # LocalRelationalAdapter (aiosqlite + asyncpg)
│   ├── blob.py             # LocalBlobAdapter (fsspec)
│   ├── channel.py          # LocalChannelAdapter (asyncio Queue / Redis pub-sub)
│   ├── function.py         # LocalFunctionAdapter
│   ├── schedule.py         # LocalScheduleAdapter (APScheduler wrapper)
│   ├── job.py              # LocalJobAdapter (asyncio-queue worker)
│   ├── asgi.py             # LocalASGIAdapter
│   └── secret.py           # LocalSecretAdapter (Dotenv)
```

`LocalRuntime` is a frozen-ish dataclass (mutable only via `register`); after `serve()` it is effectively immutable. The constructor takes `(bound: BoundPlan, app: App)` and the `from_bound_plan` factory does the dispatch walk.

`middleware.py` wraps every function/job invocation in the chain `retry → circuit_breaker → rate_limit → bulkhead → user_callable`, reading the policies off `ResourceOverrides.resilience` (a new optional field on `ResourceOverrides`, populated by `@app.function`'s kwargs). The four policy classes (`RetryPolicy`, `CircuitBreaker`, `RateLimitPolicy`, `Bulkhead`) survive from `skaal.types.compute` unchanged.

### 4.2 — `skaal/deploy/` rebuild

Layout:

```
skaal/deploy/
├── __init__.py             # re-exports pulumi_program_for, build_artefacts
├── build.py                # build_artefacts(bound, app, env) → writes ./.skaal/build/<env>/
├── program.py              # pulumi_program_for(bound, app, env) → Pulumi-API callable
├── tags.py                 # tags_for() from Decision 5
├── aws/
│   ├── __init__.py
│   ├── dynamodb.py
│   ├── postgres.py         # RDS Postgres
│   ├── redis.py            # ElastiCache
│   ├── s3.py
│   ├── lambda_fn.py        # function-kind Lambda + IAM + log group
│   ├── apigw_lambda.py     # asgi_service Lambda + APIGW HTTP API
│   ├── eventbridge.py      # schedule
│   ├── sqs_worker.py       # job
│   └── secrets.py          # secrets manager
├── local/
│   ├── __init__.py
│   ├── sqlite.py
│   ├── filesystem_blob.py
│   ├── in_process_channel.py
│   ├── uvicorn.py
│   ├── apscheduler.py
│   └── dotenv.py
└── templates/
    ├── aws/
    │   ├── Dockerfile.j2
    │   ├── handler.py.j2
    │   ├── bootstrap.py.j2
    │   └── requirements.txt.j2
    └── local/                # mostly inert — local runtime is in-process
```

`build.py` is pure templating: it renders the Jinja2 templates under `skaal/deploy/templates/aws/` and writes the rendered files to `./.skaal/build/<env>/`. The rendered tree is what Pulumi's `Function` resource points at when the deploy program runs.

`program.py`'s `pulumi_program_for` returns a *closure*, not a coroutine — Pulumi's Automation API requires the callable be invoked inside Pulumi's stack context. The closure captures `bound`, `app`, `env`, and the build artefact path; it walks `bound.resources` and dispatches to the matching `skaal/deploy/aws/<backend>.py` module.

### 4.3 — `BoundPlan` extension for fingerprint and `external`

Phase 3's `BoundPlan` carries `app`, `environment`, `resources`, `edges`. Phase 4 adds two fields:

```python
class BoundPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    app: str
    environment: str
    resources: tuple[BoundResource, ...]
    edges: tuple[Edge, ...]
    app_fingerprint: str          # NEW — copied from InferredPlan.fingerprint at bind()
    bound_fingerprint: str        # NEW — SHA-256(bytes of canonical BoundPlan) [:16]
```

`BoundResource` grows `external: bool = False`. The binder (Phase 3 `bind.py`) is amended to:

1. Carry `plan.fingerprint` through to `BoundPlan.app_fingerprint`.
2. Compute `bound_fingerprint` from the canonical-serialised resources/edges (excluding the `bound_fingerprint` field itself, same trick as `InferredPlan`).
3. Honour the `external` flag on `ResourceOverrides` and propagate to `BoundResource.external`.

The amendment to `skaal.binding` is small (~30 lines) and lands in this phase rather than re-opening Phase 3's ADR.

### 4.4 — Decorator rewire

`skaal/decorators.py` and `skaal/module.py` change as follows:

| Decorator | Phase 1 form | Phase 4 form |
|---|---|---|
| `@app.storage` | `cls.__skaal_storage__ = {...}` + `cls.__skaal_inferred__` | `cls.__skaal_inferred__` only; reads `cls.__orig_bases__` second generic and sets `overrides.backend` |
| `@app.function` | `fn.__skaal_function__ = {...}` + `fn.__skaal_inferred__` | returns `FunctionRef[P, R]`; resilience policies move to `overrides.resilience` |
| `@app.schedule` | `fn.__skaal_schedule__ = {...}` + `fn.__skaal_inferred__` | `fn.__skaal_inferred__` only |
| `@app.job` | `fn.__skaal_job__ = {...}` + `fn.__skaal_inferred__` | `fn.__skaal_inferred__` only |
| `@app.channel` | `cls.__skaal_channel__ = {...}` + `cls.__skaal_inferred__` | `cls.__skaal_inferred__` only |
| `@app.external` | (does not exist) | `cls.__skaal_inferred__` with `overrides.external = True` |

The legacy dunder reads in `skaal.relational.is_relational_model`, `skaal.blob.is_blob_model`, `skaal.storage._STORAGE_TAG`, `skaal.module._resolve_invokable`, and `skaal.schedule._register_schedule_callable` all move to read `__skaal_inferred__.kind` (or its absence). This is the "one-pass" deletion called out in ADR 030 Decision 2.

`skaal/components.py` is reduced to a backwards-incompatible no-op: `ExternalStorage` and `ExternalQueue` are deleted entirely (their reshape into `@app.external` is what this phase ships). The corresponding `__all__` entries in `skaal/__init__.py` are removed.

### 4.5 — Per-backend public import paths

One thin module per backend, re-exporting from `skaal.backends._tokens`:

```python
# skaal/backends/redis.py
from skaal.backends._tokens import Redis

__all__ = ["Redis"]
```

Twenty-five such files, one per token. The existing implementation modules already live at `skaal/backends/<name>_backend.py` (e.g. `redis_backend.py`), so the new `<name>.py` does not collide.

For backends whose name has a hyphen (`filesystem-blob`, `redis-channel`, `cloud-run`, …) the public module name uses an underscore (`filesystem_blob.py`, `redis_channel.py`, `cloud_run.py`) — Python module names cannot contain hyphens. The token's `name` field keeps the hyphenated form because that is what `skaal.toml` uses.

### 4.6 — `App.mount(path, asgi_app)`

`skaal/app.py`:

```python
class App(Module):
    def mount(self, path: str, asgi_app: ASGIApplication) -> None:
        if not path.startswith("/"):
            raise SkaalConfigError(f"mount path must start with '/': {path!r}")
        if path in self._mounts:
            raise SkaalConfigError(f"path already mounted: {path!r}")
        self._mounts[path] = asgi_app
```

`mount_asgi` and `mount_wsgi` are deleted. The recogniser in `skaal.inference.asgi` is updated to walk `app._mounts.items()` and emit one `ASGI_SERVICE` per entry, with the `path` carried in `InferredResource.overrides.options["path"]` (a new field on `ResourceOverrides`).

### 4.7 — `FunctionRef[P, R]`

`skaal/decorators.py`:

```python
P = ParamSpec("P")
R = TypeVar("R")

class FunctionRef(Generic[P, R]):
    __slots__ = ("__wrapped__", "id", "overrides")
    def __init__(self, fn: Callable[P, Awaitable[R]], id: str, overrides: ResourceOverrides):
        self.__wrapped__ = fn
        self.id = id
        self.overrides = overrides

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[R]:
        return self.__wrapped__(*args, **kwargs)

def function(*, retry=None, circuit_breaker=None, rate_limit=None, bulkhead=None):
    def decorator(fn):
        inferred = InferredResource(...)
        fn.__skaal_inferred__ = inferred
        return FunctionRef(fn, inferred.id, inferred.overrides)
    return decorator
```

The runtime / deploy layers read `.id` / `.overrides` directly; no `getattr` indirection.

Existing call sites in `examples/` switch from `await some_function(...)` to `await some_function(...)` unchanged — `__call__` proxies through. Tests assert `reveal_type(some_function("x"))` yields `Awaitable[R]`.

### 4.8 — CLI rewire

- `skaal/cli/run_cmd.py` — switches from the Phase 1 stub to a one-call wrapper around `LocalRuntime.from_bound_plan(...).serve(host, port)`.
- `skaal/cli/build_cmd.py` — replaces the Phase 1 stub with `build_artefacts(bound, app, env)`; prints the path it wrote to.
- `skaal/cli/deploy_cmd.py` — replaces the Phase 1 stub with `pulumi up` against `pulumi_program_for(...)`; on success, writes the resulting bindings back into `skaal.lock` via `write_lock(...)`.
- `skaal/cli/plan_cmd.py` — for Phase 4, prints the `BoundPlan` as a Rich table; the diff form lands in Phase 6.

All four verbs share a `_load_bound_plan(env_name)` helper that does the `infer → bind` walk.

### 4.9 — Legacy dunder deletion

In one PR following the rewire:

1. `__skaal_storage__`, `__skaal_function__`, `__skaal_schedule__`, `__skaal_channel__`, `__skaal_job__` reads removed from `skaal/storage.py`, `skaal/blob.py`, `skaal/relational.py`, `skaal/schedule.py`, `skaal/module.py`.
2. Writes removed from `skaal/decorators.py` and `skaal/module.py`.
3. The corresponding fields on the inferred-resource construction calls are dropped.
4. A `grep` gate in CI rejects any reintroduction.

### 4.10 — Tests

| File | Coverage |
|---|---|
| `tests/runtime/test_local_runtime.py` | A `BoundPlan` containing every `ResourceKind` boots a `LocalRuntime`, every adapter registers, `serve()` returns a `Starlette` app of the right shape. |
| `tests/runtime/test_adapters.py` | Per-adapter unit tests using in-memory backends: `Sqlite` for store/relational, `tempfile` for blob, `InProcessChannel` for channel. |
| `tests/runtime/test_middleware.py` | `retry`/`circuit_breaker`/`rate_limit`/`bulkhead` policies invoke the user callable the expected number of times in failure/success cases. |
| `tests/deploy/test_program.py` | `pulumi_program_for` against a sample `BoundPlan` emits the expected resource set (asserted via `pulumi.runtime.set_mocks`). Tags from `tags_for()` appear on every resource. |
| `tests/deploy/test_build.py` | `build_artefacts` renders the Jinja2 templates and writes the expected files to a temp dir. |
| `tests/deploy/test_aws_dispatch.py` | Each `skaal/deploy/aws/<backend>.py` module emits the expected Pulumi resources for a one-resource `BoundPlan`. |
| `tests/decorators/test_storage_generic.py` | `class Cache(Store[User, Redis])` populates `__skaal_inferred__.overrides.backend == "redis"`; un-pinned `Store[User]` leaves it `None`. |
| `tests/decorators/test_external.py` | `@app.external(name="legacy")` requires a type-pinned generic; setting `overrides.external = True` on the result. |
| `tests/decorators/test_function_ref.py` | `@app.function` returns a `FunctionRef`; `reveal_type` of a call site matches. |
| `tests/inference/test_mount.py` | `App.mount("/api", asgi_app)` produces one `ASGI_SERVICE` per mount; the path appears in `overrides.options["path"]`. |
| `tests/typing/test_legacy_dunders_gone.py` | `grep` gate: no occurrence of `__skaal_storage__`, `__skaal_function__`, `__skaal_schedule__`, `__skaal_channel__`, `__skaal_job__` outside `tests/` and the gate itself. |

### 4.11 — Examples and docs

Following the rewire, the surviving examples (`counter`, `todo_api`, `hello_world`, `dash_app`, `fastapi_streaming`, `file_upload_api`, `team_directory`, `session_cache`) are updated to:

1. Replace `mount_asgi` / `mount_wsgi` with `app.mount("/", asgi_app)`.
2. Drop the legacy resilience kwargs already removed at Phase 1.
3. Add one type-pinned example (`Cache(Store[Session, Redis])`) to `examples/05_task_dashboard` to exercise the second-generic syntax.

Per-example regression test (`tests/examples/test_examples_boot.py`) imports each example module and asserts that `app.infer()` returns the expected `InferredPlan` shape. Phase 5 (ADR 033) extends this to `reveal_type` assertions.

## Exit criteria

1. `skaal run` boots `examples/todo_api` against a `local` environment and serves HTTP on `localhost:8000`; every route returns the expected response.
2. `skaal deploy --env prod` (where `prod.target = aws`) provisions the AWS resources for `examples/todo_api` and `examples/counter`, with the `skaal:*` tag set on every Pulumi resource. The deploy run writes `skaal.lock` and a follow-up `skaal plan --env prod` reports zero changes unless code changed.
3. `class Cache(Store[Session, Redis])` resolves the second generic via Pylance, the binder pins it to `redis` (per Phase 3), and the runtime adapter connects to the configured Redis URL.
4. `class LegacyDb(Relational[Postgres], table=True)` decorated with `@app.external(name="legacy_db")` reads the connection from `env.backends["legacy_db"]` at runtime, and the deploy layer emits zero Pulumi resources for `LegacyDb`.
5. `grep -r "__skaal_storage__\|__skaal_function__\|__skaal_schedule__\|__skaal_channel__\|__skaal_job__" skaal/ tests/runtime tests/deploy` returns zero hits.
6. `make lint && make typecheck && make test` are green. `skaal/runtime/` and `skaal/deploy/` are included in the mypy default scope (not relaxed).
7. `notes/redesign-status.md` Phase 4 section is filled in and ticks every checkpoint below.
8. Release tag `v0.4.0-alpha.4` is **not** pushed by this PR — that is a maintainer action, tracked in the status file alongside the prior alpha tags.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| AWS-first scope balloons into AWS+GCP because counter/todo_api have aspirational GCP examples. | The deploy layer's `skaal/deploy/aws/` is the only synth implementation in this phase; `skaal/deploy/gcp/` is a `NotImplementedError` placeholder per Decision 4. The exit criterion mentions AWS only. |
| Local runtime cannot start when an optional extra is missing (e.g. `redis.asyncio`). | Each adapter `register()` defers the optional import to its own scope; the runtime fails fast with `MissingExtraError` listing the install command (`pip install skaal[aws]`, etc.) only when the adapter is invoked. |
| `PEP 696` defaults are unstable across `typing_extensions` versions. | Pin `typing_extensions>=4.12` (introduced `Default` in early 2025). The 3.11 floor in `pyproject.toml` already requires `typing_extensions` as a transitive dep through pydantic. |
| Reading `cls.__orig_bases__` to extract the backend generic misses inheritance chains, and `SQLModelMetaclass` strips it from subclasses entirely. | `Store[T, B]` / `BlobStore[B]` / `Channel[T, B]` keep `__orig_bases__`, so the decorator walks it directly. `Relational[B]` flows through `SQLModelMetaclass`; its `__class_getitem__` stashes `__skaal_backend_pin__` on the parametrised class, and the decorator reads that attribute (MRO-inherited) ahead of the `__orig_bases__` walk. A unit test covers a two-level inheritance chain (`class Cache2(Cache[Session, Redis])`). |
| Deleting the legacy dunders breaks downstream `0.3.x`-shaped consumers we missed. | The Phase 1 grep gate already passes on `Latency`/`AccessPattern`/etc.; the Phase 4 grep gate extends to legacy dunders. The CI matrix runs every example's `app.infer()` after the deletion, which catches any indirect consumer. |
| `FunctionRef` breaks `inspect.signature(some_function)` callers in the test suite. | `FunctionRef.__signature__` proxies to `inspect.signature(self.__wrapped__)`. The signature passthrough is covered in `tests/decorators/test_function_ref.py`. |
| Pulumi Automation API requires an authenticated Pulumi backend; CI cannot run `skaal deploy` end-to-end. | The deploy tests use `pulumi.runtime.set_mocks` (the official testing API) — they exercise the program callable without a real Pulumi backend. The end-to-end AWS run is documented but not gated in CI; the alpha-tag procedure runs it manually. |
| Tagging every resource increases AWS API surface (rate limits). | Tags are passed inline to the resource constructor, not via a separate `aws.ec2.Tag` resource. One API call per resource, not two. |

## Non-goals

1. **GCP deploy.** AWS-first; GCP scheduled for a 0.4.x point release with its own mini-ADR.
2. **`pyright --strict skaal/`.** Phase 5 owns it.
3. **`skaal stubs`.** Phase 5 owns it.
4. **`skaal plan` diff against `LockFile` or live state.** Phase 6 owns the diff renderer; Phase 4 ships a human-readable `BoundPlan` dump.
5. **`relational-oltp` / `relational-analytics` kind refinement.** Phase 6 owns the bytecode walker that emits the refinement.
6. **Third-party `BackendProtocol`.** v0.5 owns it.
7. **Pulumi state-backend migration tooling.** v0.5 owns it.
8. **Cross-environment promotion (`skaal promote staging prod`).** Phase 6 / 7.

## What comes next

1. **ADR 033 — Typing contract and `skaal stubs` implementation plan.** Owns Phase 5 of ADR 028 §9: the `pyright --strict` pass over `skaal/`, `examples/`, `tests/typing/`; the `tests/typing/` package and `reveal_type` assertions for every row of §6.13.3; the `skaal/stubs/` package emitting `.pyi` PEP 561 partial-stub packages; the `skaal stubs --from <src> --to <out>` CLI verb; restoration of the coverage floor from 40 back to 60.
2. After ADR 033: a 0.4.x point release ADR adding GCP deploy parity to the AWS work this ADR ships.
