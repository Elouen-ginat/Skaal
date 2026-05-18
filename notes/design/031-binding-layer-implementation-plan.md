# ADR 031 — Binding Layer and Backend Registry Implementation Plan (Phase 3)

**Status:** Proposed
**Date:** 2026-05-14
**Related:** [ADR 028](028-code-first-infra-redesign.md) (the redesign), [ADR 029](029-redesign-foundation-implementation-plan.md) (Phases 0–1), [ADR 030](030-inference-layer-implementation-plan.md) (Phase 2)
**Supersedes execution detail in:** ADR 028 §9 Phase 3

---

## Goal

Land Phase 3 of the [ADR 028](028-code-first-infra-redesign.md) redesign: a new package, `skaal.binding`, that turns an `InferredPlan` into a `BoundPlan` by combining it with an `Environment` and the `skaal.lock` file. Pure table lookup. No search. No SMT.

The output `BoundPlan` is the contract Phase 4 (runtime/deploy) consumes. Every concrete backend is named here; nothing below this layer ever picks a backend.

## Scope

In scope:

- The `skaal.binding` package with five modules — `model.py`, `environment.py`, `lock.py`, `defaults.py`, `registry.py`, plus a `bind.py` containing the pure `bind(plan, env, lock)` function.
- The typed `Backend` token base in `skaal/backends/_base.py`, plus token subclasses for each backend the `0.4.0-alpha` line ships: `Sqlite`, `Postgres`, `Redis`, `DynamoDB`, `Firestore`, `S3`, `Gcs`, `FilesystemBlob`, `InProcessChannel`, `RedisChannel`, `Asyncio`, `Lambda`, `CloudRun`, `Uvicorn`, `Apscheduler`, `EventBridgeLambda`, `CloudSchedulerCloudRun`, `SqsLambdaWorker`, `CloudTasksCloudRun`, `DotenvSecret`, `AwsSecretsManager`, `GcpSecretManager`.
- The defaults table from ADR 028 §6.3 lifted into `skaal/binding/defaults.py` as a `Mapping[ResourceKind, Mapping[Target, type[Backend]]]` literal.
- The frozen-pydantic models from ADR 028 §6.3: `Target`, `BackendConfig`, `ResourceOverride`, `Environment`, `LockEntry`, `LockFile`, `BoundResource`, `BoundPlan`.
- The `BackendEntry`, `BackendCapabilities`, and `REGISTRY` from ADR 028 §6.12.
- Binding errors in `skaal.errors`: `TypePinViolation`, `BackendKindMismatch`, `BackendNotAvailableForTarget`, `UnknownBackendError`.
- A TOML loader for `skaal.toml` → `dict[str, Environment]` and the round-trippable `skaal.lock` reader/writer.
- Tests under `tests/binding/` covering each binding branch and round-tripping the pydantic surface.

Out of scope (each lands in its own phase/ADR):

- The `Store[T, B]` / `Relational[B]` / `BlobStore[B]` / `Channel[T, B]` backend generic parameter. Phase 3 ships the `Backend` token tree the parameter binds against, but the primitive classes keep their existing single-parameter generics until Phase 4 wires the generics through the runtime. The `__skaal_inferred__` attribute already carries `ResourceOverrides`, but the `backend_token` field on it stays `None` until Phase 4 introduces the syntax.
- `@app.external` decorator — Phase 3 leaves it parked. The binding layer's `Environment.backends: dict[str, BackendConfig]` is the mechanism `@app.external` will use in Phase 4 to attach a user-supplied connection.
- Kind-aware refinement of `Relational` (`relational-oltp` vs. `relational-analytics`) from ADR 028 §6.5.2. The Phase 3 walker emits a single `RELATIONAL` `ResourceKind`; the inference of *which* kind requires the bytecode-level call-graph walker scheduled for Phase 6. `BackendKindMismatch` is implemented at the binder but only fires for explicit declarations.
- Pulumi codegen against the `BoundPlan`. Phase 4 owns this.
- `pyright --strict` over `skaal.binding.*`. Phase 5 owns the global strict pass.
- Live SDK imports inside each backend token (e.g. `from google.cloud.bigquery import Client`). Phase 3 wires the typing contract with `NativeClient = Any` for backends whose SDK is an optional extra; the typed escape (`Cache.native()` returning `redis.asyncio.Redis`) gets its concrete generic in Phase 5 alongside the typing pass.

## Decision 1 — `BoundPlan` and friends are pydantic, frozen, `extra="forbid"`

The same contract as `skaal.inference` (ADR 030 Decision 1):

1. JSON-schema, validation, equality, and `model_dump_json()` come for free.
2. `frozen=True` makes mutation a runtime error — `BoundPlan` is the deterministic input to deploy codegen, which assumes it is byte-stable.
3. `extra="forbid"` keeps unknown TOML keys from silently riding into the plan.

The model surface in `skaal.binding.model` is exactly the eight types from ADR 028 §6.3: `Target` (a `StrEnum`), `BackendConfig`, `ResourceOverride`, `Environment`, `LockEntry`, `LockFile`, `BoundResource`, `BoundPlan`.

`LockFile.entries` is keyed by a `tuple[str, str]` (`(env_name, resource_id)`); pydantic serialises this as a list of `[env_name, resource_id, entry]` triples to keep JSON faithful, and the TOML on-disk form uses the nested form from ADR 028 §6.10 (`[entries.<env>."<resource_id>"]`). The TOML/JSON conversion lives in `skaal.binding.lock` and is tested for byte-stable round-tripping.

## Decision 2 — `Backend` tokens are real classes, not strings

ADR 028 §6.12 is explicit: backends are typed Python class tokens *and* registry entries, both. Strings appear only inside `skaal.toml` and are looked up by `token.name`.

```python
# skaal/backends/_base.py
from typing import Any, ClassVar, Generic, TypeVar

NativeClientT = TypeVar("NativeClientT")

class Backend(Generic[NativeClientT]):
    """Base for every backend type token (ADR 028 §6.12)."""

    name: ClassVar[str]
    kinds: ClassVar[frozenset[str]]
    NativeClient: ClassVar[type[Any]]   # narrowed in concrete subclasses
```

Concrete tokens live one-per-module under `skaal/backends/<name>.py`, named in PascalCase:

```python
# skaal/backends/redis.py
from skaal.backends._base import Backend

class Redis(Backend[Any]):
    name = "redis"
    kinds = frozenset({"store", "channel"})
    NativeClient = object        # narrowed to redis.asyncio.Redis in Phase 5
```

Why narrow `NativeClient` to `object` in Phase 3:

- Most backends (`Postgres`, `BigQuery`, `Firestore`, `DynamoDB`, …) live behind optional extras (`skaal[aws]`, `skaal[gcp]`). Importing the SDK at the token module's top level would fail when the extra isn't installed, breaking the registry import.
- Phase 5's typing pass adds a `TYPE_CHECKING`-guarded import that gives Pylance the real type without forcing the runtime import. Phase 3's narrower contract is "the token exists, the registry resolves it, `.native()` returns *something*"; the concrete type lands when strict typing does.

## Decision 3 — The binder is a pure function over frozen inputs

```python
def bind(plan: InferredPlan, env: Environment, lock: LockFile) -> BoundPlan:
    bound = tuple(_bind_resource(r, env, lock) for r in plan.resources)
    return BoundPlan(app=plan.app, environment=env.name, resources=bound, edges=plan.edges)
```

`_bind_resource` walks the four branches from ADR 028 §6.3 in order, every branch is enumerated explicitly, and each branch returns a `BoundResource` immediately. The function is pure (no side effects, no globals beyond the immutable `DEFAULTS` and `REGISTRY` tables).

Branches (in priority order):

1. **Type-pinned class** (`res.overrides.backend` names a registered token). Override and lock entries that name a different backend → `TypePinViolation`. Otherwise emit `BoundResource(backend=token.name, pinned=True)`.
2. **Lock entry** for `(env.name, res.id)`. Emit `BoundResource(backend=entry.backend, pinned=True)`.
3. **Env override** in `env.overrides[res.id]`. Emit `BoundResource(backend=override.backend, pinned=False)`.
4. **Defaults table** lookup `DEFAULTS[res.kind][env.target]`. Emit `BoundResource(backend=DEFAULTS[res.kind][env.target].name, pinned=False)`.

Each branch additionally validates:

- The chosen backend is in `REGISTRY` (else `UnknownBackendError`).
- The chosen backend's `targets` includes `env.target` (else `BackendNotAvailableForTarget`).
- The chosen backend's `kinds` covers `res.kind` (else `BackendKindMismatch`).

The validation runs *after* the branch picks a backend, so `TypePinViolation` (the explicit user-intent error) wins over the structural ones. Validation order inside a single branch is `target` first, then `kind`, then `options` against `options_schema`.

## Decision 4 — The defaults table is a literal, not a function

`skaal/binding/defaults.py` is one module with one constant:

```python
from skaal.backends.sqlite import Sqlite
from skaal.backends.postgres import Postgres
from skaal.backends.dynamodb import DynamoDB
# … one import per backend token

DEFAULTS: Mapping[ResourceKind, Mapping[Target, type[Backend]]] = MappingProxyType({
    ResourceKind.STORE: MappingProxyType({
        Target.LOCAL: Sqlite,
        Target.AWS:   DynamoDB,
        Target.GCP:   Firestore,
    }),
    ResourceKind.RELATIONAL: MappingProxyType({
        Target.LOCAL: Sqlite,
        Target.AWS:   RdsPostgres,
        Target.GCP:   CloudSqlPostgres,
    }),
    # … one row per ResourceKind from §6.3
})
```

`MappingProxyType` makes the table read-only at the import boundary so a misbehaving module cannot mutate the contract. Adding or changing a row is an ADR-gated change, enforced by a test that asserts the table's frozen shape.

Every cell points at a `type[Backend]`, not a string, so the import-time wiring is type-checked end-to-end. The binder reads `.name` off the token when it needs the on-disk string form.

## Decision 5 — The registry is a tuple, not a discovery mechanism

`skaal/binding/registry.py` is one module with one constant:

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
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    token: type[Backend]
    targets: frozenset[Target]
    capabilities: BackendCapabilities
    options_schema: type[BaseModel]

REGISTRY: tuple[BackendEntry, ...] = (
    BackendEntry(token=Sqlite,   targets={LOCAL},           capabilities=..., options_schema=SqliteOptions),
    BackendEntry(token=Redis,    targets={LOCAL, AWS, GCP}, capabilities=..., options_schema=RedisOptions),
    BackendEntry(token=Postgres, targets={LOCAL, AWS, GCP}, capabilities=..., options_schema=PostgresOptions),
    BackendEntry(token=DynamoDB, targets={AWS},             capabilities=..., options_schema=DynamoDBOptions),
    # … one row per backend
)
```

Three accessors live alongside it for cheap reads:

```python
def lookup(name: str) -> BackendEntry: ...        # by token.name, raises UnknownBackendError
def lookup_token(token: type[Backend]) -> BackendEntry: ...  # by class identity
def tokens_for(kind: ResourceKind, target: Target) -> tuple[BackendEntry, ...]: ...
```

There is no entry-point discovery, no TOML catalog overlay, no per-environment plugin set. The tuple is the contract. Adding a new backend is one PR (subclass, entry, test); third-party backends re-enter through a separate `BackendProtocol` work item in a later version.

## Decision 6 — `skaal.toml` is loaded by `skaal.binding.environment`, not by `skaal.settings`

`skaal.settings.SkaalSettings` continues to own the `[tool.skaal]` / `SKAAL_*` env-var surface (CLI flags, target, region, output dir). It does *not* own `skaal.toml`, which carries the per-environment binding state.

`skaal.binding.environment` exposes:

```python
def load_environments(path: Path | None = None) -> dict[str, Environment]: ...
def load_environment(name: str, path: Path | None = None) -> Environment: ...
```

`path` defaults to `skaal.toml` in the current working directory (and walks up to find it, like `find_pyproject` in `skaal.settings`). The file is optional; an absent `skaal.toml` produces a single `Environment(name="local", target=Target.LOCAL)` baseline so `skaal run` works out of the box.

Why two modules instead of one: `SkaalSettings` already handles per-stack overlays for the CLI verbs (the `0.3.x` form). Phase 4's runtime rewire will replace those callers with `load_environment(...)` directly, at which point the overlap goes away. Phase 3 keeps the two side-by-side rather than mid-flight refactoring the CLI.

## Implementation

### 3.1 — `skaal/backends/_base.py`

The `Backend` base class from Decision 2. One file, ~30 lines. Imports nothing from `skaal.binding` (the binding layer imports the tokens, not the other way around — keeps the dependency arrow one-way).

### 3.2 — Backend token modules

All token classes live in a single `skaal/backends/_tokens.py` module — one `Backend` subclass per backend, 25 subclasses total, each a 4-line class body (`name`, `kinds`, `NativeClient`). The module is purely declarative; it imports only `Backend` from `skaal.backends._base` and has no transitive dependencies on the impl files.

Public per-token import paths (`from skaal.backends.redis import Redis`, as quoted in ADR 028 §6.5) are deferred to Phase 4 once the second-generic syntax exists to consume them — Phase 3's binder reads tokens by class identity from `_tokens.py` and by `name` from the registry, neither of which depends on the user-facing import path. The Phase 4 ADR will land thin re-export modules (`skaal/backends/redis.py` → `from skaal.backends._tokens import Redis`) without touching the canonical class location.

Initial token set (matching the defaults table):

| Token class | Kinds | Targets |
|---|---|---|
| `Sqlite` | `{store, relational}` | `{LOCAL}` |
| `Postgres` | `{relational}` | `{LOCAL, AWS, GCP}` |
| `Redis` | `{store, channel}` | `{LOCAL, AWS, GCP}` |
| `DynamoDB` | `{store}` | `{AWS}` |
| `Firestore` | `{store}` | `{GCP}` |
| `S3` | `{blob}` | `{AWS}` |
| `Gcs` | `{blob}` | `{GCP}` |
| `FilesystemBlob` | `{blob}` | `{LOCAL}` |
| `InProcessChannel` | `{channel}` | `{LOCAL}` |
| `RedisChannel` | `{channel}` | `{LOCAL, AWS, GCP}` |
| `Sqs` | `{channel}` | `{AWS}` |
| `Pubsub` | `{channel}` | `{GCP}` |
| `Asyncio` | `{function}` | `{LOCAL}` |
| `Lambda` | `{function}` | `{AWS}` |
| `CloudRun` | `{function, asgi_service}` | `{GCP}` |
| `Uvicorn` | `{asgi_service}` | `{LOCAL}` |
| `ApigwLambda` | `{asgi_service}` | `{AWS}` |
| `Apscheduler` | `{schedule, job}` | `{LOCAL}` |
| `EventBridgeLambda` | `{schedule}` | `{AWS}` |
| `CloudSchedulerCloudRun` | `{schedule}` | `{GCP}` |
| `SqsLambdaWorker` | `{job}` | `{AWS}` |
| `CloudTasksCloudRun` | `{job}` | `{GCP}` |
| `DotenvSecret` | `{secret}` | `{LOCAL}` |
| `AwsSecretsManager` | `{secret}` | `{AWS}` |
| `GcpSecretManager` | `{secret}` | `{GCP}` |

The existing implementation modules (`local_backend.py`, `redis_backend.py`, `dynamodb_backend.py`, …) keep their names and are untouched by Phase 3. The runtime/deploy hookups that bridge a token to its implementation land in Phase 4.

A `RdsPostgres` and `CloudSqlPostgres` distinction in the defaults table maps to a single `Postgres` token in Phase 3 — the AWS/GCP-managed flavour is a deploy-layer detail (Phase 4). Phase 3's defaults table cells point at `Postgres` for both AWS and GCP relational defaults.

### 3.3 — `skaal/binding/model.py`

The eight pydantic types from ADR 028 §6.3. `Target` is a `StrEnum` with `LOCAL`, `AWS`, `GCP`. `BackendConfig` carries free-form `dict[str, Any]` options validated against the backend's `options_schema` at construction time (the binder calls `entry.options_schema.model_validate(env.backends[token.name].options)` and re-attaches the validated form to the `BoundResource`).

### 3.4 — `skaal/binding/registry.py`

`Backend`, `BackendCapabilities`, `BackendEntry`, the `REGISTRY` tuple, and the three accessors from Decision 5. The options-schema classes (`SqliteOptions`, `RedisOptions`, …) are defined inline as minimal pydantic models — most backends accept `region`, `endpoint`, `emulator`, and a backend-specific identifier (`project`, `dataset`, `table_prefix`). The full backend-option surface lands incrementally in Phase 4 as each deploy template needs it; Phase 3 ships permissive (`extra="allow"`) schemas plus a test asserting every registered backend has a schema present.

### 3.5 — `skaal/binding/defaults.py`

The `DEFAULTS` literal from Decision 4. Wrapped in `MappingProxyType` for read-only access. A test asserts:

- Every `ResourceKind` is a key.
- Every `Target` appears under every key.
- Every cell value is a `type[Backend]` registered in `REGISTRY`.

### 3.6 — `skaal/binding/environment.py`

`load_environments(path)` and `load_environment(name, path)` from Decision 6. The TOML parser is `tomllib` (stdlib on 3.11+). Validation produces an `Environment` with `extra="forbid"`; unknown top-level keys in `[env.<name>]` raise `SkaalConfigError` with the offending path.

When `skaal.toml` is absent, returns `{"local": Environment(name="local", target=Target.LOCAL)}`.

### 3.7 — `skaal/binding/lock.py`

`load_lock(path)`, `write_lock(path, lock)`. The on-disk form is TOML matching ADR 028 §6.10:

```toml
version = 1

[entries.prod."acme.users:Users"]
backend = "dynamodb"
pinned_at = "2026-05-12T14:00:00Z"
pinned_by = "alice@acme.com"
fingerprint = "abc123…"
```

The reader normalises the `[entries.<env>."<resource_id>"]` form into `LockFile.entries: dict[tuple[str, str], LockEntry]` keyed by `(env, resource_id)`. The writer round-trips. Absent file → empty `LockFile`.

### 3.8 — `skaal/binding/bind.py`

The pure `bind(plan, env, lock)` function from Decision 3 plus `_bind_resource`. ~80 lines including the validation branches.

### 3.9 — `skaal/errors.py` additions

New subclasses of `SkaalConfigError`:

- `TypePinViolation(resource_id: str, declared: str, requested: str)` — raised when an env override or lock entry names a backend different from the declared type-pin.
- `BackendKindMismatch(resource_id: str, backend: str, required_kind: str)` — raised when the chosen backend's `kinds` does not cover the resource's required kind.
- `BackendNotAvailableForTarget(backend: str, target: str)` — raised when the chosen backend's `targets` does not include the active `Environment.target`.
- `UnknownBackendError(name: str, valid: tuple[str, ...])` — raised when a string in `skaal.toml` does not match any registered `token.name`.

Each carries `__cause__` plumbing and a one-line user-facing message; the CLI's Rich formatter renders them.

### 3.10 — `skaal/__init__.py` exports

`__all__` grows by the public binding-layer names:

```python
from skaal.binding import (
    BackendCapabilities,
    BackendConfig,
    BackendEntry,
    BoundPlan,
    BoundResource,
    Environment,
    LockEntry,
    LockFile,
    ResourceOverride,
    Target,
    bind,
    load_environment,
    load_environments,
    load_lock,
    write_lock,
)
from skaal.backends._base import Backend
```

The `Backend` base class joins the public surface so user code can write `from skaal import Backend` at the top of a backend module without reaching into the registry's private module path.

### 3.11 — Tests under `tests/binding/`

| File | Coverage |
|---|---|
| `test_model.py` | Every pydantic type round-trips through `model_dump_json()` → `model_validate_json`. `extra="forbid"` rejects unknown fields. `Target` enum has the three variants. `LockFile.entries` tuple-key serialises and re-validates. |
| `test_defaults.py` | Every `ResourceKind` × `Target` cell is populated. Every cell points at a token registered in `REGISTRY`. The table is read-only (mutating an entry raises). |
| `test_registry.py` | Every token in `DEFAULTS` is in `REGISTRY`. Every entry has a `targets` frozenset, a `BackendCapabilities`, and an `options_schema`. `lookup("unknown")` raises `UnknownBackendError` listing valid names. |
| `test_bind.py` | Defaults branch: an un-pinned `Store[User]` resource in `Environment(target=LOCAL)` binds to `Sqlite`. Lock branch: a lock entry for `(env, res_id)` overrides the defaults table. Env override branch: `env.overrides[res_id]` overrides the defaults table. Type-pin branch: when `overrides.backend` is set on the `InferredResource`, the lock and env overrides may not name a different backend (raises `TypePinViolation`). Kind mismatch: a `RELATIONAL` resource against a `BLOB`-only backend raises `BackendKindMismatch`. Target mismatch: a `LOCAL` env asking for `DynamoDB` raises `BackendNotAvailableForTarget`. |
| `test_environment.py` | `load_environments` against a fixture TOML returns the right `Environment` shape. Unknown top-level keys raise. Absent file produces the `local` baseline. |
| `test_lock.py` | `write_lock` followed by `load_lock` returns an equal `LockFile`. Round-tripping is byte-stable for a given input. |

## Exit criteria

1. `bind(plan, env, lock)` returns a `BoundPlan` for an `InferredPlan` containing every `ResourceKind`; the bound plan validates against `BoundPlan.model_json_schema()`.
2. `make lint && make typecheck && make test` are green. `skaal/binding/` and `skaal/backends/_base.py` are included in the mypy default scope (not relaxed).
3. `notes/redesign-status.md` Phase 3 section is filled in and ticks every checkpoint below.
4. Release tag `v0.4.0-alpha.3` is **not** pushed by this PR — that is a maintainer action, tracked in the status file alongside the Phase 1/2 alpha tags.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| The `Backend` token tree forces every backend's SDK to be importable at registry load. | Tokens declare `NativeClient = object` (Phase 3) and narrow to the concrete SDK type in Phase 5 behind `TYPE_CHECKING`. Optional-extra SDKs are never imported at module top level. |
| The defaults table goes stale as new backends land. | The Phase 3 test suite asserts `DEFAULTS[kind][target]` is registered, and a `BackendKindMismatch` test ensures the kind/target axes still align. A new backend that wants to move a default cell files an ADR (per CLAUDE.md "Adding a new backend"). |
| The lock-file TOML keying (`tuple[str, str]`) is awkward to round-trip. | `lock.py` handles the nested form (`[entries.<env>."<resource_id>"]`) explicitly and a test round-trips it. Pydantic's tuple-key default would emit a list of triples; the on-disk form is the readable one. |
| `Environment` and `skaal.toml` collide with the existing `SkaalSettings.for_stack` machinery. | Decision 6: `SkaalSettings` keeps `[tool.skaal]` and `SKAAL_*` env vars. `skaal.toml` is a new file, owned by `skaal.binding.environment`. The two coexist until Phase 4 retires the legacy CLI surface. |
| Type-pinning logic is invoked before Phase 4 wires `Store[T, B]` syntax. | The binder reads `res.overrides.backend` (a string), not a `backend_token` field. Phase 4 will populate that string from the second generic parameter; Phase 3 ships the validation path so the wiring is a one-line decorator change later. The Phase 3 type-pin test constructs an `InferredResource` with `overrides.backend = "redis"` manually. |

## Non-goals

1. `Store[T, B]` / `Relational[B]` backend-generic syntax. Phase 4 owns the decorator rewire that populates `overrides.backend` from the backend generic parameter (the second on `Store` / `BlobStore` / `Channel`; the only one on `Relational`).
2. Pulumi codegen against the `BoundPlan`. Phase 4 owns this.
3. `@app.external` decorator. Phase 4 owns it.
4. `pyright --strict skaal/`. Phase 5 owns the global strict pass.
5. Kind refinement of `RELATIONAL` into `relational-oltp` / `relational-analytics`. Phase 6 owns the bytecode walker that emits the refinement.
6. CLI integration of `skaal plan` against `BoundPlan`. Phase 6 owns the diff command; Phase 3's binder is callable from a one-line CLI bridge but the verb is still stubbed.

## What comes next

1. **ADR 032 — Runtime/deploy on `BoundPlan` implementation plan.** Owns Phase 4 of ADR 028 §9: the decorator rewire (`Store[T, B]` second generic, `@app.external`, `FunctionRef[P, R]`), the local runtime rebuild on top of `BoundPlan`, the Pulumi codegen, and the deletion of the legacy `__skaal_storage__` / `__skaal_function__` / `__skaal_schedule__` dunders.
2. After ADR 032: `pyright --strict` for `skaal.binding.*` is added to the CI matrix as a separate gate from the wider mypy run.
