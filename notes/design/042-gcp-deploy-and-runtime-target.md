# ADR 042 — GCP deploy and runtime target (Phase 8)

- **Status:** accepted
- **Date:** 2026-05-18
- **Supersedes:** none
- **Superseded by:** none
- **Related:** ADR 028 (redesign), ADR 029 (foundation plan), ADR 031 (binding), ADR 032 (runtime/deploy on `BoundPlan`), ADR 041 (runtime registry)

## Context

ADR 028 §6 commits to three deploy targets — `local`, `aws`, `gcp`. Phases 3–7 built out the binding layer, the AWS deploy target (Phase 4 §4.2), and the AWS runtime target (Phase 4 §4.14). The GCP token tree has shipped since Phase 3 (`Firestore`, `Gcs`, `Pubsub`, `CloudRun`, `CloudSchedulerCloudRun`, `CloudTasksCloudRun`, `GcpSecretManager`, plus `Postgres` and `RedisChannel` shared with AWS), and the binding registry's import-time consistency check already enforces a default for every `(ResourceKind, Target)` cell — so binding against `target = "gcp"` resolves end-to-end. What is missing is:

1. A `BigQuery` typed `Backend` token, so users can write `class Sales(Table[BigQuery], table=True)` and ADR 028 §12 criterion 6 becomes provable.
2. A `skaal.deploy.gcp` package mirroring `skaal.deploy.aws`: per-resource Pulumi synth modules driven by typed `GcpConfig`, exposed as a `DeployTarget` via the existing registry.
3. A `skaal.runtime.gcp` package mirroring `skaal.runtime.aws`: cold-start binding wirers and backend factories keyed off env vars populated by the GCP synth modules.

Without (2) and (3), `skaal deploy --env prod` against `target = "gcp"` raises `No deploy target registered for 'gcp'`. With them, GCP becomes a first-class deploy target alongside AWS.

## Decision

This phase delivers — as a single landed slice — the BigQuery backend token, the `skaal.deploy.gcp` package, and the `skaal.runtime.gcp` package, behind an in-tree plugin registration that mirrors AWS exactly. The shape is identical to AWS so the existing `pulumi.automation` driver, the `skaal where` resolver, the typed config overlay, and the runtime cold-start path all work without changes.

### 1. BigQuery typed `Backend` token

Add `class BigQuery(Backend[object])` to `skaal/backends/_tokens.py` with `name = "bigquery"` and `kinds = frozenset({"relational"})`. Register a `BackendSpec(token=BigQuery, targets=frozenset({Target.GCP}))` in `skaal/binding/registry.py` with `capabilities=BackendCapabilities(partitioning=True)`. Do **not** make it a default — `Postgres` remains the GCP default for `relational`; BigQuery is opt-in via class-level pin (`class Sales(Table[BigQuery], table=True)`) or env-level override.

Add a thin re-export module `skaal/backends/bigquery.py` so users write `from skaal.backends.bigquery import BigQuery` (matches the pattern set in Phase 4 §4.5 for the 25 other tokens). Add a `BigQueryBackend` factory module `skaal/backends/bigquery_backend.py` that wires the runtime adapter to `google.cloud.bigquery.Client`; `.native()` returns that client.

Add `BigQuery` to `ALL_TOKENS` (the consistency-check tuple) and to `skaal/__init__.py`'s `__all__`. Add a `tests/typing/test_reveal_types.py` row asserting that `class Sales(Table[BigQuery], table=True)` flows the pin through to `ResourceOverrides.backend == "bigquery"`.

### 2. `skaal.deploy.gcp` package

Mirror `skaal.deploy.aws` file-for-file:

```
skaal/deploy/gcp/
├── __init__.py          # Builds GcpTarget, calls register_target(TARGET)
├── _target.py           # GcpTarget(BaseDeployTarget) — target=Target.GCP, _config_cls=GcpConfig
├── _config.py           # GcpConfig + sub-configs (one section per synth)
├── _cloud_run.py        # CloudRunSynth abstract base (mirrors LambdaSynth)
├── _where.py            # GCP_* provider type constants + console URL builders
├── firestore.py         # STORE synth
├── gcs.py               # BLOB synth
├── pubsub.py            # CHANNEL synth (Pubsub token)
├── secrets.py           # SECRET synth (GcpSecretManager token)
├── postgres.py          # RELATIONAL synth (Cloud SQL)
├── bigquery.py          # RELATIONAL analytics synth (BigQuery token)
├── cloud_run_fn.py      # FUNCTION synth (Cloud Run service, no event source)
├── cloud_run_asgi.py    # ASGI_SERVICE synth (Cloud Run service exposing /{path})
├── cloud_scheduler.py   # SCHEDULE synth (Cloud Scheduler → Cloud Run URL)
└── cloud_tasks.py       # JOB synth (Cloud Tasks queue → Cloud Run worker)
```

Templates live under `skaal/deploy/templates/gcp/`:

- `Dockerfile.j2` — `python:3.11-slim` base, `uv pip install -r pyproject.toml`, `CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]`.
- `server.py.j2` — Starlette app mounting each `FUNCTION` as a POST endpoint at `/_skaal/fn/<name>`, the user's `ASGI_SERVICE` at its declared `path`, and JOB / SCHEDULE handlers at `/_skaal/job/<name>` / `/_skaal/schedule/<name>`. Cloud Scheduler and Cloud Tasks call these by URL.
- `pyproject.toml.j2` — copies the user's dependency set into the container image.

Required Pulumi extras: `pulumi`, `pulumi_gcp`, `pulumi_docker`. Listed in `GcpTarget._required_extras`.

#### `GcpConfig` sections (mirrors `AwsConfig`)

| Section | Defaults |
|---|---|
| `iam` | service-account display name, `project` (resolved from env) |
| `artifact_registry` | location (default `us`), repo format `DOCKER`, immutable tags off |
| `cloud_run_defaults` | timeout_s=300, memory="512Mi", cpu="1", max_instances=10, port=8080, min_instances=0 |
| `cloud_run_asgi_defaults` | timeout_s=300, memory="1Gi", cpu="1" |
| `cloud_run_job_defaults` | timeout_s=600, memory="512Mi" |
| `firestore` | location_id="nam5", type="FIRESTORE_NATIVE", env_var_prefix="SKAAL_TABLE_" |
| `gcs` | location="US", storage_class="STANDARD", env_var_prefix="SKAAL_BUCKET_" |
| `pubsub` | message_retention_duration="86400s", env_var_prefix="SKAAL_CHANNEL_", env_var_suffix="_TOPIC" |
| `secrets` | replication="automatic", env_var_prefix="SKAAL_SECRET_", env_var_suffix="_NAME" |
| `postgres` | tier="db-f1-micro", database_version="POSTGRES_16", db_name="skaal", username="skaal", env_var_prefix="SKAAL_DB_" |
| `bigquery` | location="US", env_var_prefix="SKAAL_BQ_", env_var_suffix="_DATASET" |
| `cloud_scheduler` | fallback_schedule="0 * * * *", time_zone="Etc/UTC" |
| `cloud_tasks` | rate_limits dispatch_per_second=10, max_concurrent_dispatches=100, env_var_prefix="SKAAL_JOB_", env_var_suffix="_QUEUE" |

Overrides come through `[env.<name>.backends.gcp.options.<section>]` — same path AWS uses, just keyed by `gcp` instead of `aws`. The `GcpTarget.stack_config(env)` method writes `gcp:project` and `gcp:region` (when present) so Pulumi picks them up.

#### `CloudRunSynth` abstract base

Mirrors `LambdaSynth`:

- `_pre_scaffold(ctx)` — hook for resources that must exist before the service is constructed (Cloud Tasks worker case).
- `_build_scaffold(ctx, extra_env)` — emits the Artifact Registry repo, the container image, the service account, the Cloud Run service itself, IAM bindings.
- `_event_source(ctx, scaffold, pre)` — overridden by `CloudSchedulerSynth` (HTTP target → Scheduler job) and `CloudTasksSynth` (HTTP target → Tasks queue).
- `_env_vars(ctx, scaffold, pre)` — same role as the AWS variant.

Concrete subclasses: `CloudRunFunctionSynth` (no event source), `CloudRunAsgiSynth` (no event source, but uses `cloud_run_asgi_defaults`), `CloudSchedulerSynth` (Scheduler → Run), `CloudTasksSynth` (Tasks → Run).

#### `skaal where` resolvers

Constants in `_where.py`:

```python
GCP_CLOUDRUN_SERVICE = "gcp:cloudrunv2/service:Service"
GCP_FIRESTORE_DATABASE = "gcp:firestore/database:Database"
GCP_STORAGE_BUCKET = "gcp:storage/bucket:Bucket"
GCP_PUBSUB_TOPIC = "gcp:pubsub/topic:Topic"
GCP_SECRETMANAGER_SECRET = "gcp:secretmanager/secret:Secret"
GCP_SQL_INSTANCE = "gcp:sql/databaseInstance:DatabaseInstance"
GCP_BIGQUERY_DATASET = "gcp:bigquery/dataset:Dataset"
GCP_CLOUDSCHEDULER_JOB = "gcp:cloudscheduler/job:Job"
GCP_CLOUDTASKS_QUEUE = "gcp:cloudtasks/queue:Queue"
```

Each console URL builder resolves to the relevant `https://console.cloud.google.com/...` page using `project` + `region` (or `location` for BigQuery / Pub/Sub).

### 3. `skaal.runtime.gcp` package

Mirror `skaal.runtime.aws`:

```
skaal/runtime/gcp/
├── __init__.py          # Re-exports wire_app_from_environment
├── target.py            # GCP_RUNTIME_TARGET + register_builtin_runtime_target()
├── backends.py          # build_firestore_store, build_gcs_blob, build_bigquery_relational, ...
└── bootstrap.py         # wire_app_from_environment (cold-start hook)
```

The runtime target registers:

| `(ResourceKind, backend_name)` | Factory |
|---|---|
| `(STORE, "firestore")` | `build_firestore_store` → `FirestoreBackend(project, collection)` |
| `(STORE, "redis")` | reuses `skaal.runtime.aws.backends.build_redis_store` |
| `(BLOB, "gcs")` | `build_gcs_blob` → `GcsBlobBackend(bucket)` |
| `(RELATIONAL, "postgres")` | reuses Postgres factory, reads connection via `SKAAL_DB_<slug>_CONN` |
| `(RELATIONAL, "bigquery")` | `build_bigquery_relational` → `BigQueryBackend(project, dataset)` |
| `(CHANNEL, "pubsub")` | `build_pubsub_channel` → `PubsubChannelBackend(project, topic)` |
| `(CHANNEL, "redis-channel")` | reuses Redis-channel factory |

Cold-start `wire_app_from_environment` reads the per-target env-var schema from the `BoundPlan`'s connection layer (same as AWS).

#### BigQuery is local-runnable

Per ADR 028 §12 criterion 6, `class Sales(Table[BigQuery], table=True)` must run against real BigQuery *locally* (using `env.local.backends.bigquery.options`). The local runtime target therefore also registers `build_bigquery_relational` for the `(RELATIONAL, "bigquery")` cell — the binder routes the resource through binding-time pin checking, but the local adapter accepts the `bigquery` backend name and the factory wires the official `google.cloud.bigquery.Client` from `GOOGLE_APPLICATION_CREDENTIALS`. This is the same pattern Redis already follows (local runtime accepts `redis` when the user pins it).

### 4. Plugin registration

`skaal/deploy/gcp/__init__.py` calls `register_target(TARGET)` at import time, exactly like `skaal/deploy/aws/__init__.py`. `skaal/runtime/_registry.py`'s `_ensure_builtin_targets_loaded` is extended to also import `skaal.runtime.gcp.target` and call its `register_builtin_runtime_target`. Both registrations are silent overwrites so test re-imports don't break.

### 5. Optional extras

`pyproject.toml` `[project.optional-dependencies]`:

- `gcp` group already exists for runtime SDKs (`google-cloud-firestore`, `google-cloud-storage`, `google-cloud-pubsub`, `google-cloud-bigquery`, `google-cloud-secret-manager`).
- Add a new `gcp-deploy` group: `pulumi`, `pulumi-gcp`, `pulumi-docker`, `pulumi-command`.
- The deploy target's `__init__.py` swallows `ModuleNotFoundError` for the Pulumi extras (mirrors AWS) and registers an empty target so read-only flows like `skaal where` still resolve.

### 6. Example

`examples/bigquery_sales/` ships with:

- `app.py` — `class Sale(Relational[BigQuery], table=True)` with a few fields, `@app.function` that inserts a row, `@app.function` that runs a SQL aggregate via `await Sale.native().query("SELECT ...")`.
- `skaal.toml` — `[env.local.backends.bigquery.options]` with a `project` and `dataset`.
- `README.md` — instructions for the maintainer-run §7.9 BigQuery smoke.

### 7. Tests

- `tests/backends/test_bigquery.py` — token registration, kind/target metadata, `class Sales(Relational[BigQuery])` pin flow.
- `tests/deploy/test_gcp_dispatch.py` — registry + target wiring (registers `GcpTarget` with the expected backend set).
- `tests/deploy/test_gcp_synth.py` — mocked Pulumi (`pulumi.runtime.set_mocks`) covering one synth per kind; same shape as `tests/deploy/test_aws_synth.py`.
- `tests/runtime/test_gcp_target.py` — backend factory registration, env-var-driven wiring (no real GCP calls).
- `tests/typing/test_reveal_types.py` — `Relational[BigQuery]` pin assertion.

### 8. Out of scope

- **Real-GCP smoke run** — gated behind `SKAAL_RUN_BIGQUERY_SMOKE=1` per ADR 035 Decision 3. A maintainer with GCP credentials runs it after Phase 8 lands.
- **Cloud Run job kind (Run jobs, not services)** — using Cloud Tasks → Run service is enough for the v0.4.0 contract. Cloud Run Jobs (the batch resource) can be a follow-up if the queue-pull semantics need tightening.
- **Workload Identity Federation** — Phase 8 wires service accounts directly; WIF is a follow-up.
- **VPC connectors / private services** — Phase 8 deploys to the public Cloud Run URL; private networking is a follow-up.

## Consequences

- `v0.4.0` ships with a working `gcp` target end-to-end at the *code* level — every synth module, every runtime adapter, every test that does not require a real GCP project.
- ADR 028 §12 criterion 6 becomes testable: `await Sales.native()` resolves to `google.cloud.bigquery.Client` in pyright and at runtime.
- The full real-GCP validation (a `gcloud auth` smoke run of `examples/bigquery_sales/`) remains a maintainer action tied to ADR 035 §7.9.
- Adding a third deploy target (Azure, on-prem, …) becomes a copy of `skaal/deploy/gcp/` with the synth modules rewritten — the framework's extensibility model is now exercised twice and the protocol is load-bearing.

## Update protocol

When the GCP Phase 8 slice lands on the `redesign` branch:

- Tick the §7 checklist items in `notes/redesign-status.md`.
- Tick ADR 028 §12 criterion 6 once the BigQuery `.native()` row in `tests/typing/test_reveal_types.py` passes pyright.
- Leave §7.9 (BigQuery smoke recorded in `docs/whats-new.md`) unticked until a maintainer runs it.
