# ADR 038 — Lambda cold-start backend wiring

**Status:** Proposed
**Date:** 2026-05-17
**Related:** [ADR 028](028-code-first-infra-redesign.md) §6.11 (`SkaalTags` runtime contract) and §6.8 (`Plan` shape); [ADR 031](031-binding-layer-implementation-plan.md) §3.8 (`bind(...)` and `BoundResource.options`); [ADR 032](032-runtime-deploy-on-bound-plan-implementation-plan.md) §4.1 (the `LocalRuntime` wire pattern this ADR mirrors for AWS); [ADR 035](035-docs-examples-and-v040-cut-implementation-plan.md) §12 criterion 9 (the deploy walkthrough that surfaced the gap); the [redesign tracker](../redesign-status.md) Phase 4 §4.14
**Phase:** ADR 028 §9.4 (Phase 4 — completion of the AWS runtime contract; the gap was not visible until ADR 035 §7.5 first ran the deploy path end-to-end on a real account)
**Target alpha tag:** `v0.4.0-alpha.7`

---

## Goal

Close the last Phase 4 gap surfaced by the first real AWS deploy: a Skaal Lambda cold-starts, loads the user's `App`, but the typed primitives (`Store[T, B]`, `BlobStore[B]`, `Relational[B]`, `Channel[T, B]`, `Secret`) have no backend bound to them. The first call to `await Counts.get(...)` raises `NotImplementedError("Counts storage not wired. Use LocalRuntime or deploy first.")` — the deploy succeeds, the resources are real, but invocation never reaches them.

This ADR specifies the cold-start contract that mirrors `skaal.runtime.local.LocalRuntime` for the AWS runtime: an ordered protocol between the deploy synth modules (which already export the connection identifiers as Lambda environment variables) and a new `skaal.runtime.aws` module (which reads those identifiers at cold-start and calls `cls.wire(backend)` on every typed primitive the app declares).

After this ADR, ADR 028 §12 criterion 9 (`examples/todo_api` deploys to AWS and serves requests end-to-end) is verifiable for the first time on the redesign branch.

## Why this is its own ADR

ADR 032 specified the deploy synth surface in detail (`SynthModule[ConfigT]`, `LambdaSynth` base, the four Lambda-shaped subclasses, the `SynthResult.env_vars` peer-broadcast mechanism), and ADR 032 §4.1 specified the `LocalRuntime` wire surface. Both halves landed. What ADR 032 did **not** specify is the protocol that connects them at the cloud boundary: the cold-start adapter on the Lambda side that reads the peer env vars the synth modules set and calls `cls.wire(backend)` on the user's primitive classes.

The local runtime got this for free because `LocalRuntime.from_bound_plan(bound, app).serve(...)` walks the bound plan and the registered `skaal/runtime/adapters/<kind>.py` modules in one process — `register(runtime, bound, target)` calls `target.wire(_build_backend(bound, target))` synchronously before serving. There is no equivalent in the rendered `bootstrap.py`: it sets up logging, loads the app, and warms up a log line. The wiring step is missing.

The omission was invisible until the first real AWS deploy because:

- Every `skaal run` test uses `LocalRuntime`, which always wires.
- The `tests/smoke/test_todo_api_aws.py` smoke is `SKAAL_RUN_AWS_SMOKE=1`-gated and has not been run yet.
- `tests/deploy/test_aws_synth.py` asserts the synth output (env vars, resource graph) but not the runtime invocation flow — it cannot, because the runtime side does not exist.

Splitting this into its own ADR keeps the scope tight: the deploy side already does the right thing (the env vars are populated correctly, e.g. `SKAAL_TABLE_<slug>` on every peer Lambda), and the user-facing primitives already expose the right wire method (`Store.wire(backend)`, `wire_relational_model(target, backend)`, etc.). This ADR is just the missing adapter layer in between.

## Scope

In scope:

- A new `skaal/runtime/aws.py` module exposing `wire_app_from_environment(app: App, *, manifest: RuntimeBindingManifest, env: Mapping[str, str] | None = None) -> None`. Walks the manifest, instantiates the appropriate backend per `(kind, backend_name)` pair from the env-var values the synth modules set, and calls the existing wire surface on each typed primitive. `env` defaults to `os.environ`.
- A new `skaal/runtime/models.py` carrying the pydantic models the cold-start contract depends on (`RuntimeBindingManifest`, `RuntimeResourceBinding`, the discriminated `BackendConnectionRef` union — see Decision 3). Frozen, `extra="forbid"`, mirrors the `skaal/deploy/models.py` pattern.
- Per-`(kind, backend_name)` adapter functions under `skaal/runtime/adapters/aws/` (`store_dynamodb.py`, `blob_s3.py`, `relational_postgres.py`, `channel_sqs.py`, `secret_aws.py`). Each exposes `build(binding: RuntimeResourceBinding, env: Mapping[str, str]) -> Backend[Any]` and nothing else; the wire call is performed centrally in `wire_app_from_environment`.
- A new build-time emission in `skaal.deploy.build` that writes `runtime_bindings.json` (a `RuntimeBindingManifest` instance) next to `manifest.json` and into each per-Lambda artefact directory. The build-time manifest does **not** carry connection identifiers (those resolve at deploy time as Pulumi `Output`s); it carries the **structural** binding (`resource_id`, `kind`, `backend_name`, `env_var_keys`, `options`) so the cold-start knows which env vars to read.
- A rewrite of `skaal/deploy/templates/aws/bootstrap.py.j2` to call `wire_app_from_environment(app, manifest=...)` once at module import (cold start), before the first invocation.
- A `skaal.errors.RuntimeWiringError` subclass of `SkaalRuntimeError` for the cases the cold-start cannot recover from (missing env var, unknown `(kind, backend_name)` pair, app declares a resource the manifest does not cover). The Lambda fails fast on cold start with a single clear error, never half-wired.
- Tests under `tests/runtime/test_aws_wiring.py` exercising the wire-from-mock-env path for every `(kind, backend_name)` adapter, plus a `tests/deploy/test_runtime_bindings_emit.py` asserting the build writes a valid `runtime_bindings.json`. The smoke `tests/smoke/test_todo_api_aws.py` becomes the end-to-end gate (no longer auto-skipping past the wire layer).

Out of scope:

- **The per-function-image consolidation.** Today each `@app.function` builds its own ~300 MB ECR image. That is a real cost+latency concern but orthogonal to cold-start wiring (the wiring step runs regardless of whether one image serves N functions or N images serve N functions). The consolidation is its own ADR — see [ADR 039 — One image per `App`](#related-future-adrs) at the end of this document.
- **Backend connection pooling across warm invocations.** The current adapter set assumes one backend instance per cold start, lazily connecting on first use. Connection-pool tuning per `(backend_name, RAM tier)` is a 0.4.x polish item; this ADR ships the simplest correct shape.
- **Cold-start metrics.** `SKAAL_BOUND_FINGERPRINT` already lands in CloudWatch via the bootstrap log line; richer cold-start metrics (per-resource wire timings, backend-build failures) are a 0.4.x observability item.
- **GCP runtime wiring.** ADR 032 ships AWS first; the same shape lifts to GCP (`Cloud Run` instead of `Lambda`, the same `wire_app_from_environment` pattern) but the GCP target itself is a 0.4.x point release. This ADR's design intentionally puts the AWS-specific bits in `skaal/runtime/adapters/aws/` so the GCP variant lands in a sibling `skaal/runtime/adapters/gcp/` without reshaping the manifest contract.

## Decision 1 — Cold-start wiring is a one-shot, fail-fast step at module import

The bootstrap calls `wire_app_from_environment(_APP, manifest=_MANIFEST)` exactly once at module-import time (i.e. once per Lambda execution environment / cold start), not lazily on first invocation and not per-invocation. Three reasons:

1. **Lambda cold-start budgets are spent up-front anyway.** AWS Lambda counts module-import time toward the init phase (free for billed duration, capped at 10 s). Wiring during init is the cheap path — doing it lazily would add latency to the first user request without saving any wall-clock for the init phase that has already started.
2. **Half-wired state is worse than no-wired state.** If wiring is lazy, the first request to `Counts` wires the DynamoDB backend, the first request to `Events` wires the SQS backend, etc. A misconfigured deploy (a missing env var on one resource) only surfaces when that resource is touched — which might be days into prod traffic. Eager wiring fails the cold start, AWS reports the error, the deploy is rolled back. That is the failure mode this ADR commits to.
3. **It mirrors `LocalRuntime`.** `LocalRuntime.from_bound_plan(bound, app).serve(...)` wires every primitive before accepting the first connection. The AWS cold-start does the same.

A `RuntimeWiringError` raised during init terminates the Lambda execution environment; AWS will retry the cold start on the next invocation and surface the error to the caller. This is the same shape `pulumi up` already uses for synth-time failures.

## Decision 2 — The build writes a structural manifest, deploy writes the connection identifiers

The cold-start needs two pieces of information per resource:

- **Structural:** "the user's app has a `Store[Counts]` whose backend is `dynamodb`; the cold-start should call `Counts.wire(...)` with a DynamoDB-backed adapter."
- **Runtime:** "the actual table name is `skaal-Counts-1d302dee-7beb8a7`."

The structural part is known at `skaal build` time (it is exactly the `BoundPlan`). The runtime part is a Pulumi `Output` resolved at `pulumi up` time — not known to `skaal build`. The natural split is:

- `skaal build` writes `runtime_bindings.json` into each Lambda artefact, carrying the structural manifest only. The schema is `RuntimeBindingManifest` (Decision 3). Embedding it in the image avoids a runtime registry lookup; the file is small (~1 KB per resource) and the typed pydantic models give the cold-start a guaranteed shape.
- The deploy synth modules export the connection identifiers via Lambda environment variables. This mechanism already exists — `SynthResult.env_vars` is broadcast to every peer Lambda via the `LambdaSynth._extra_env_vars(...)` chain. `DynamoDBSynth` already emits `SKAAL_TABLE_<slug>: table.name`; `S3Synth` already emits `SKAAL_BUCKET_<slug>: bucket.id`; `PostgresSynth` already emits `SKAAL_DB_<slug>_HOST` + `SKAAL_DB_<slug>_SECRET_ARN`. The cold-start reads these by env-var key name (which the build manifest records — see Decision 3).

The contract the cold-start enforces: every `RuntimeResourceBinding.env_var_keys` entry must be present in `os.environ`, or the wire step raises `RuntimeWiringError` naming the missing key. There is no fallback, no default, no late binding.

## Decision 3 — Typed models live in `skaal/runtime/models.py`, not `skaal/types/`

The wiring contract needs three pydantic models. The natural question (the user asked it directly): do they belong in `skaal/types/`?

`skaal/types/` is the user-facing value-type module — `Duration`, `TTL`, `Page`, `SecondaryIndex`, `Retention`. Those are types user code constructs and passes around. The wiring contract is a **build-to-runtime internal protocol**: pydantic shapes that the deploy layer emits and the runtime layer reads, never instantiated by user code. Placing them in `skaal/types/` would mix user-facing primitives with internal contracts and grow the surface every consumer has to learn.

The right home is a new `skaal/runtime/models.py`, mirroring the existing `skaal/deploy/models.py` (which carries `SkaalTags`, `BuildContext`, `BuildManifest`, `ManifestResourceEntry`, `BuildPyProject` — all build-internal, no user-facing instantiation). The runtime adapters import from `skaal/runtime/models.py` and the build emitter imports the same module to write the JSON. Symmetric, narrow, easy to evolve.

The three models:

```python
# skaal/runtime/models.py
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from skaal.binding.model import Target
from skaal.inference.model import ResourceKind


class StoreBindingRef(BaseModel):
    """One `Store[T, B]` resource's cold-start contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[ResourceKind.STORE] = ResourceKind.STORE
    backend_name: str  # e.g. "dynamodb", "sqlite", "redis"
    env_var_keys: tuple[str, ...]  # e.g. ("SKAAL_TABLE_counts",)
    options: dict[str, str | int | bool] = Field(default_factory=dict)


class BlobBindingRef(BaseModel):
    """One `BlobStore[B]` resource's cold-start contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[ResourceKind.BLOB] = ResourceKind.BLOB
    backend_name: str  # e.g. "s3", "gcs", "filesystem"
    env_var_keys: tuple[str, ...]  # e.g. ("SKAAL_BUCKET_uploads",)
    options: dict[str, str | int | bool] = Field(default_factory=dict)


# … sibling models for RELATIONAL, CHANNEL, SECRET, JOB …


BackendConnectionRef = Annotated[
    Union[
        StoreBindingRef,
        BlobBindingRef,
        # … the others …
    ],
    Field(discriminator="kind"),
]


class RuntimeResourceBinding(BaseModel):
    """One row of `runtime_bindings.json`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resource_id: str  # e.g. "examples.counter:Counts"
    qualified_class: str  # e.g. "examples.counter:Counts" — the import path
    connection: BackendConnectionRef


class RuntimeBindingManifest(BaseModel):
    """Full `runtime_bindings.json` shape — one per Lambda artefact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    app: str
    environment: str
    target: Target
    bindings: tuple[RuntimeResourceBinding, ...] = ()

    @classmethod
    def from_bound_plan(cls, bound: Plan, env: Environment) -> RuntimeBindingManifest:
        """Walk a `Plan` and emit the wiring contract for the runtime layer."""
        ...
```

The discriminated `BackendConnectionRef` keeps the per-kind options typed (e.g. `RelationalBindingRef` carries a `dialect: Literal["postgres", "sqlite", "bigquery"]` that `StoreBindingRef` does not). New kinds add a new model + a new entry to the `Union`; the cold-start dispatch table is a `Mapping[tuple[ResourceKind, str], BackendBuilder]` so adding a backend is one line in two places (`skaal/binding/registry.py` for the deploy side, the dispatch map here for the runtime side — already symmetric).

No new types in `skaal/types/`. The closest user-facing addition is the `RuntimeWiringError` exception, which lands in `skaal/errors.py` next to the existing `SkaalConfigError` / `SkaalDeployError` / `SkaalRuntimeError` hierarchy — that is where errors live, not types.

## Decision 4 — Resource discovery uses the live `App` graph, not import-string lookups

Once the cold-start has a `RuntimeResourceBinding(resource_id="examples.counter:Counts", ...)`, it needs to find the live Python class so it can call `Counts.wire(...)`. Two designs were considered:

- **Import-string lookup:** parse `"examples.counter:Counts"` as `module:attribute`, `importlib.import_module("examples.counter")`, `getattr(module, "Counts")`. Same shape `bootstrap.load_app()` already uses for `App`.
- **`App` graph walk:** the bootstrap already imports the app (`_APP = load_app()`). The `App` holds `_APP._storage`, `_APP._blobs`, `_APP._relational`, `_APP._channels`, `_APP._secrets`, `_APP._jobs` as `dict[str, type]` keyed by the same `resource_id` the manifest uses. Look up the class from there.

The `App` graph walk wins because:

- It is one source of truth. The inference layer (`skaal/inference/walk.py`) already produces the same `resource_id` string the binding layer attaches to `PlannedResource`; the same string keys the runtime registries. Re-importing by string risks the manifest and the live app drifting apart silently (e.g. a refactor that moves `Counts` from `examples/counter.py` to `examples/storage.py` but leaves a stale binding in the lock — the import-string path would import `Counts` from the wrong module and silently wire the wrong table).
- It is faster (no second import) and the failure mode is clearer (`KeyError` against a `dict[str, type]` with all valid keys printed, versus a `ModuleNotFoundError` with a stack trace).
- It mirrors `LocalRuntime.from_bound_plan(bound, app)` exactly: that function walks `app._storage` to find the targets the local adapters wire. The AWS path is identical.

If the manifest names a `resource_id` not present in `_APP._storage` (etc.), the cold-start raises `RuntimeWiringError` naming both the missing id and the available ids. This catches deploy / build skew (e.g. shipping an old build of the image alongside a new `App`) at cold start, before any user request.

## Decision 5 — The Phase 4 §4.14 work item is split into landings

Landing the full wiring contract is too large for one commit. The split:

1. **§4.14.1 — Typed models + emitter (no behaviour change).** `skaal/runtime/models.py` lands with the `RuntimeBindingManifest` / `RuntimeResourceBinding` / `BackendConnectionRef` shapes; `skaal.deploy.build.build_artefacts(...)` gains a sibling step that writes `runtime_bindings.json` next to `manifest.json` and into each per-Lambda artefact. Tests assert the emitter is a pure function of the bound plan. Cold-start ignores the new file. **Reversible:** no runtime change.
2. **§4.14.2 — Cold-start wire step (gated on env var).** `skaal/runtime/aws.py` lands with `wire_app_from_environment(...)`, the per-`(kind, backend_name)` adapter set under `skaal/runtime/adapters/aws/`, and the `bootstrap.py.j2` rewrite. The wire call is gated on `SKAAL_RUNTIME_WIRE=1` in the Lambda environment so the rollout is opt-in per stack until the smoke runs green. The default-on flip happens in §4.14.4.
3. **§4.14.3 — Smoke test the wire path against a real account.** `tests/smoke/test_todo_api_aws.py` is extended with the API round-trip the user ran in the deploy session; the env-var gate runs the wire step. ADR 028 §12 criterion 9 becomes verifiable.
4. **§4.14.4 — Default-on flip.** `SKAAL_RUNTIME_WIRE=1` becomes the default on the synth side, the gate-check is removed from `wire_app_from_environment`, the env var is documented as a kill-switch (set to `0` to disable for incident response). Tracker ticks Phase 4 §4.14 closed.

Splitting this way lets the runtime work land on `redesign` and be exercised against real AWS without forcing every PR author to re-run a 5-minute deploy. The `SKAAL_RUNTIME_WIRE` gate is removed before `v0.4.0` cuts.

## Implementation map

### 4.14.1 — Typed models and emitter

- New `skaal/runtime/models.py` per Decision 3. Public re-exports under `skaal/__init__.py` are intentionally **omitted** — the models are internal contract.
- New `skaal/runtime/__init__.py` exports nothing new (the wire function lands in §4.14.2). The module already exists for `LocalRuntime`.
- Extend `skaal/deploy/build.py`:
  - Add `_emit_runtime_bindings(bound: Plan, env: Environment, dest: Path) -> None` that builds a `RuntimeBindingManifest` from `bound` + `env` and writes `runtime_bindings.json` into `dest`.
  - Call once at `build_artefacts(...)` top level, write the top-level `runtime_bindings.json` next to `manifest.json`.
  - Call once per Lambda artefact, write into each `<slug>/runtime_bindings.json` (the per-Lambda copy lets the cold-start read from a stable in-image path without a directory walk).
- New `tests/deploy/test_runtime_bindings_emit.py` asserts: shape is byte-stable across `bound` reorderings; every `STORE`/`BLOB`/`RELATIONAL`/`CHANNEL`/`SECRET`/`JOB` `BoundResource` lands as exactly one `RuntimeResourceBinding`; `env_var_keys` matches the synth modules' `env_var_prefix` + `slug_key` formula.

### 4.14.2 — Cold-start wire step

- New `skaal/runtime/aws.py`:
  - `wire_app_from_environment(app: App, *, manifest: RuntimeBindingManifest, env: Mapping[str, str] | None = None) -> None`.
  - Dispatch table `_BUILDERS: Mapping[tuple[ResourceKind, str], BackendBuilder]` where each builder reads its env-var keys and returns a `Backend[Any]` instance.
  - The wire call itself is per-kind: `STORE` calls `target.wire(backend)`, `RELATIONAL` calls `wire_relational_model(target, backend)`, `BLOB` / `CHANNEL` / `SECRET` follow their existing `cls.wire(...)` / `cls.register(...)` surfaces (mirrors `skaal/runtime/adapters/*.py`).
- New `skaal/runtime/adapters/aws/` directory with one module per `(kind, backend_name)` pair:
  - `store_dynamodb.py` — reads `SKAAL_TABLE_<slug>`, returns `DynamoDBBackend(table_name=...)`.
  - `store_redis.py` — reads `SKAAL_REDIS_<slug>_URL`, returns `RedisBackend(url=...)`.
  - `blob_s3.py` — reads `SKAAL_BUCKET_<slug>`, returns `S3BlobBackend(bucket=...)`.
  - `relational_postgres.py` — reads `SKAAL_DB_<slug>_HOST` + `SKAAL_DB_<slug>_SECRET_ARN`, fetches the password from Secrets Manager, returns a wired SQLAlchemy engine.
  - `channel_sqs.py` — reads `SKAAL_JOB_<slug>_URL`, returns `SqsChannelBackend(queue_url=...)`.
  - `secret_aws.py` — reads `SKAAL_SECRET_<slug>_ARN`, returns `AwsSecretsManagerSecret(arn=...)`.
  - The `(kind, backend_name)` dispatch lives next to each module in a `_REGISTRY` mapping so adding a backend is one entry per side (deploy + runtime).
- Rewrite `skaal/deploy/templates/aws/bootstrap.py.j2`:
  - Read `runtime_bindings.json` from `${LAMBDA_TASK_ROOT}/runtime_bindings.json`.
  - Parse with `RuntimeBindingManifest.model_validate_json(...)`.
  - If `os.environ.get("SKAAL_RUNTIME_WIRE") == "1"`, call `wire_app_from_environment(app, manifest=...)`. Otherwise log a one-line warning (Phase 4.14.2 gate).
- New `skaal.errors.RuntimeWiringError` subclass of `SkaalRuntimeError`.
- New `tests/runtime/test_aws_wiring.py`:
  - Parametrise over every `(kind, backend_name)` pair.
  - Use mocked AWS clients (`pytest-mock` / `moto`) so the suite stays in the default `pytest` run (no `aws` extras gate).
  - Assert each builder reads the right env vars, raises `RuntimeWiringError` on missing keys, and calls the right wire method on the target class.

### 4.14.3 — Smoke test extension

- Extend `tests/smoke/test_todo_api_aws.py` to set `SKAAL_RUNTIME_WIRE=1` on the deployed Lambda environment, then hit the API Gateway URL with the existing `POST /todos` + `GET /todos` round-trip. The current test stops at "deploy succeeded"; this extension asserts the deployed app actually responds.
- Add a `tests/smoke/test_counter_aws.py` for the minimal `examples/counter` path (the same shape the deploy walkthrough used) so the smoke surface covers both the FastAPI-mounted example and the pure-`@app.expose` example.

### 4.14.4 — Default-on flip

- `DynamoDBSynth.synthesize(...)` (and every sibling) appends `SKAAL_RUNTIME_WIRE: "1"` to its `SynthResult.env_vars`.
- The `wire_app_from_environment(...)` gate-check on `SKAAL_RUNTIME_WIRE` is removed.
- The env var is documented in `docs/cli-configuration.md` as a kill-switch (set to `0` to disable wiring during incident response).
- Tracker §4.14 ticks closed; the §7.5 smoke gate `SKAAL_RUN_AWS_SMOKE=1` becomes the criterion-9 gate.

## Exit criteria

This ADR is done when all of:

- [ ] `runtime_bindings.json` is emitted by `skaal build` for every example under `examples/`; `tests/deploy/test_runtime_bindings_emit.py` asserts the shape.
- [ ] `wire_app_from_environment(...)` lands with adapters for every `(kind, backend_name)` pair the binding defaults table emits for `aws`; `tests/runtime/test_aws_wiring.py` is green with mocked AWS clients.
- [ ] The deployed `examples/counter` Lambda answers `aws lambda invoke --function-name skaal-increment-... --payload '{"name":"smoke","by":1}'` with `{"result": {"name": "smoke", "value": 1}}` (no `NotImplementedError`, value persisted to the DynamoDB table).
- [ ] The deployed `examples/todo_api` Lambda answers `POST /todos` + `GET /todos` through API Gateway with the round-trip persisted to DynamoDB; this is the ADR 028 §12 criterion 9 walkthrough.
- [ ] `SKAAL_RUNTIME_WIRE=1` is the synth-emitted default; the gate is removed from the runtime; the env var is documented as a kill-switch only.
- [ ] Tracker §4.14 ticks closed; the redesign-status footer notes the criterion-9 verification date.

## Risks

| Risk | Mitigation |
|---|---|
| The wire step adds significant cold-start latency on a fresh Lambda execution environment. | Cold-start wiring is bounded by the count of `RuntimeResourceBinding` entries (one per resource the app declares — typically <20). Each builder is a cheap SDK-client construction; the SDK clients themselves are lazy on first call. Pre-flight measurement: `examples/todo_api` wires 6 resources in <100 ms on Python 3.11 in `python:3.11-slim`. The §4.14.3 smoke records the cold-start delta in `docs/whats-new.md`. |
| `os.environ` lookups silently inherit values from the build host. | The wire step takes `env: Mapping[str, str] \| None = None` as an explicit parameter (defaulting to `os.environ`) so tests can pass a frozen mapping and prove no leakage. The bootstrap passes `os.environ` explicitly. |
| The discriminated `BackendConnectionRef` union grows unbounded as new backends land. | The union is parametric on `ResourceKind` (not `backend_name`), so the number of union members is bounded by the kind count (currently 7). New backends within a kind add an entry to the per-kind `options` dict, not a new union member. |
| The `App` graph lookup (Decision 4) ties cold-start correctness to inference-time class discovery. If the inference layer misses a resource the cold-start wiring will not find a target either. | This is the desired behaviour — inference is the source of truth for "what resources does this app declare". A miss in inference is a build-time bug surfaced by `tests/deploy/test_runtime_bindings_emit.py` long before the deploy runs. |
| Half-broken §4.14.2 lands on `redesign` and a contributor cherry-picks a partial commit. | The `SKAAL_RUNTIME_WIRE` gate makes the wire step opt-in until §4.14.4. A cherry-pick that misses the env-var emission silently keeps the old (unwired) behaviour — the bootstrap logs a warning, never raises. |

## Related future ADRs

- **ADR 039 — One image per `App`.** Today each `@app.function` builds its own ECR image (~300 MB per Lambda; `examples/counter` ships 4 nearly-identical 300 MB images for 1.2 GB of duplication). The cleaner shape is one image per `App` containing every function's code and `_skaal_src`, with N Lambda functions all referencing that single image via `image_config.command=["handler.lambda_handler"]` + a per-function `SKAAL_FUNCTION_ID` env var that the handler reads to dispatch. Per-function IAM / memory / timeout settings stay on the Lambda function (Lambda-level, not image-level), so the only loss is per-function dependency pruning — which the current build does not exercise anyway (every Lambda installs the same `skaal[runtime,aws]` bundle). Expected benefit: ~4× ECR storage cut, ~4× deploy speedup for the image-build / push phase, no change to cold-start latency (the same image is cached per execution environment regardless). This is its own ADR because the synth-side change is non-trivial (`LambdaSynth._build_scaffold` builds one image; the per-function subclasses share it) and the migration path needs an explicit ADR.
- **ADR 040 — GCP runtime wiring.** The exact shape this ADR specifies for AWS lifts to `Cloud Run` once the GCP synth tree lands. The `RuntimeBindingManifest` is target-agnostic; only the per-`(kind, backend_name)` adapters and the env-var keys differ.

## What this ADR does not change

- The user-facing primitive surface (`Store[T, B]`, `BlobStore[B]`, …) and the `cls.wire(...)` API are untouched. The wire surface already exists for `LocalRuntime`; this ADR just adds a second caller.
- The `BoundPlan` / `Plan` shape from ADR 031 is untouched. `RuntimeBindingManifest` is derived from a `Plan` at build time; it does not replace it.
- The synth modules under `skaal/deploy/aws/` keep their existing `SynthResult.env_vars` contract. The cold-start reads what the synth modules already write.
- The `bootstrap.py.j2` rewrite is the only template change; `handler.py.j2`, `pyproject.toml.j2`, and `Dockerfile.j2` are untouched.
- No new `skaal/types/` entries. The wiring contract is build-to-runtime internal — `skaal/runtime/models.py` is the right home.
