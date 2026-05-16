# Redesign status (ADR 028)

This file is the canonical answer to "where are we in the redesign?" It carries state only — design decisions live in the implementation ADRs (029, 030, …). See [ADR 029](design/029-redesign-foundation-implementation-plan.md) for the update protocol.

**Current alpha:** `v0.4.0a0` declared in `pyproject.toml`; no alpha tag pushed yet.
**Branch:** `claude/plan-redesign-strategy-A5ixu` (de-facto `v0.4.0-alpha` working branch). Promotion/rename to `v0.4.0-alpha` on `origin` is a maintainer action.
**Last updated:** 2026-05-16 — The Phase 4 §4.11 type-pinned `Store[T, Redis]` example demonstration now lives in `examples/session_cache.py`: `Sessions` and `Tokens` subclass `Store[SessionRecord, Redis]` / `Store[TokenRecord, Redis]` (second generic pinned to the `Redis` backend token), `__skaal_default_ttl_seconds__` carries the class-level TTL the legacy `retention=` decorator kwarg used to set, and per-call `Sessions.set(..., ttl="45m")` overrides still work. The pin flows end-to-end: inference reports `ResourceOverrides.backend == "redis"` and `bind()` against both `local` and `aws` environments emits `BoundResource(backend="redis", pinned=True)`. The constraint-era kwargs (`read_latency`, `durability`, `access_pattern`, `retention`) that have been gone from `@app.storage`'s signature since Phase 1 were also stripped out of `examples/01_hello_world`, `examples/07_file_upload_api`, `examples/session_cache`, and `examples/team_directory` so the working subset of the example suite imports cleanly again. The original §4.11 target was `examples/05_task_dashboard/app.py`, but that 2235-line example still imports `VectorStore`, `Agent`, `EventLog`, `Saga`, `Durability`, `Persistent`, `Scale`, `ScaleStrategy`, and `@handler` — every one of which was deleted in Phase 1 — so the type-pin demonstration moved to the smaller, runnable `session_cache.py` and the deeper rewrite of `03_dash_app`, `05_task_dashboard`, `04_mesh_counter`, and `mesh_counter` is deferred to the Phase 7 docs/examples rewrite. The previous milestone — `Module.invoke` / `Module.invoke_stream` wired end-to-end through `LocalRuntime` — finished the in-process invocation contract called out as a hole in the `skaal run examples/todo_api` commit. `RuntimeState` gained `invokables: dict[str, Callable[..., Awaitable[Any]]]` and `invokable_streams: dict[str, Callable[..., AsyncIterator[Any]]]`; the function adapter populates both (regular coroutines under `invokables` with the resilience chain wrapped in, async-generator-shaped functions under `invokable_streams` raw — retry on a partially-consumed stream is ill-defined and deferred). `LocalRuntime.invoke(name, kwargs)` and `LocalRuntime.invoke_stream(name, kwargs)` are the two new dispatch entry points; the registry keys are the `<app.name>.<bare>` qualified form `Module._resolve_invokable` returns, so the bare-name vs qualified-name mismatch that caused the first attempt to fail with `KeyError` is gone. `build_asgi()` now calls `app._bind_runtime(self)` before running startup hooks and `app._unbind_runtime(self)` in the lifespan teardown, so `app.invoke(...)` works from inside route handlers (and raises `RuntimeError("No active Skaal runtime is bound…")` outside the serve loop, as before). Async-generator-shaped `@app.function`s no longer get an HTTP route — the existing route adapter would have `await`-ed an `AsyncGenerator`, which is broken; users surface streams through their mounted FastAPI / Starlette routes plus `app.invoke_stream(...)`. Six new tests under `tests/runtime/test_local_runtime.py` cover `invoke` / `invoke_stream` happy paths, the `KeyError` shape, the no-HTTP-route guarantee for streams, and the bind/unbind lifecycle. `examples/06_fastapi_streaming` is now a working example (the third — `counter`, `todo_api`, `fastapi_streaming`); `curl -N "localhost:8000/chat?prompt=hello%20streaming%20world"` returns the SSE-shaped `data: hello`/`data: streaming`/`data: world`/`data: [done]` stream. The previous milestone — `skaal run examples/todo_api` end-to-end fix — landed earlier on the same branch. The first implementation cut followed ADR 028 §6.5.1's two-generic `Relational[T, B]` shape, but it forced users to declare every field twice (once on a companion DTO `T`, once on the SQL class body) for no runtime gain; the shape was reduced to a single backend generic before merging. `Relational` now sits on `SQLModel` + `Generic[B]` — the class body *is* the row schema, just like a plain SQLModel — and `__class_getitem__` stashes `__skaal_backend_pin__` onto the parametrised class so user code like `class Comments(Relational[Postgres], table=True)` flows the `postgres` pin into `ResourceOverrides.backend` without any env override. The same `_extract_backend_pin` helper now serves all four primitives — `SQLModelMetaclass` strips `__orig_bases__` on subclasses, so the helper reads `__skaal_backend_pin__` (MRO-inherited from the parametrised class) ahead of the `__orig_bases__` walk used by `Store` / `BlobStore` / `Channel`. `Relational` is exported from `skaal/__init__.py` and `__all__`. ADR 028 §6.5.1 was rewritten around `class Sales(Relational[BigQuery], table=True)` (companion `Sale(BaseModel)` removed) with a short "Note on shape" recording the design change; every other `Relational[Sale, BigQuery]` / `Relational[T, B]` / `Relational[Sale]` reference across ADRs 028, 030, 031, 032 was rewritten to the single-generic form. Tests under `tests/test_relational_primitive.py` and `tests/decorators/test_backend_pin.py` cover pinned / un-pinned / `Backend`-default / multi-parametrisation cases (331 total pass; pulumi-dependent tests still skip when the `deploy,aws` extras aren't installed). The previous milestone — Phase 4 Pulumi synth half landed on `claude/continue-redesign-typed-vars-VHYzp`, with two follow-up refactors. The first formalized the multi-target shape (`DeployTarget` Protocol, registry, typed configs). The second introduced a plugin architecture so external libraries can contribute infrastructure modules: `skaal.plugins.SkaalPlugin` is a runtime-checkable Protocol exposed via the ``skaal.plugins`` entry-point group, `PluginRegistry.add_target` / `add_synth` / `add_backend` wire a plugin's contributions into the live deploy + binding registries, and `load_plugins()` runs lazily on first `get_target(...)` / `lookup(...)` / `tokens_for(...)`. `BaseDeployTarget.register_synth(module)` allows late synth registration on an already-built target; `skaal.binding.registry.register_backend(entry)` adds a `BackendEntry` at runtime (idempotent for same-token re-registration; raises on name collisions). A broken plugin logs a warning and is skipped — it never breaks Skaal's own boot. Now installing `pip install skaal-aws-aurora` (hypothetical) with one `[project.entry-points."skaal.plugins"]` line adds the Aurora backend + synth to AWS with zero core edits. The deploy layer now exposes a `DeployTarget` Protocol (runtime-checkable) plus a `register_target` / `get_target` registry — adding a new cloud target (GCP, Azure, …) is dropping a new `skaal/deploy/<target>/` package that constructs a `BaseDeployTarget` subclass and self-registers at import time. Synth dispatch, stack naming, stack-config wiring, optional-extra resolution, and config loading all flow through the registered target instance; `skaal.deploy.program.pulumi_program_for(bound, env, build_dir)` and `synthesize_stack(...)` look up the target via `env.target` and dispatch through `target.lookup_synth(...)`. Per-synth-module declaration is now `SPEC: SynthSpec` (backend names + supported kinds) plus a `synthesize(ctx) -> SynthResult` function; `BaseDeployTarget.from_modules(...)` walks a tuple of modules to build the dispatch table. Every cloud constant that used to be a string / int literal moved into typed pydantic models (`AwsLambdaConfig`, `DynamoDBConfig`, `PostgresConfig`, `RedisConfig`, `S3Config`, `SqsConfig`, `SecretsConfig`, `IamConfig`, `EcrConfig`, `ApiGatewayConfig`, `EventBridgeConfig`, aggregated in `AwsConfig`); users override any field via ``[env.<name>.backends.aws.options.<section>]`` in `skaal.toml` and `AwsTarget.config_for(env)` overlays the values at deploy time. The 10 AWS synth modules read everything off `ctx.config.<section>` — no hardcoded ARNs, instance classes, memory sizes, log retentions, schedule fallbacks, or env-var prefixes left in synth code. `SynthContext[ConfigT]` is generic over the target config so each synth signature carries its config type. `skaal/cli/deploy_cmd.py` reads `target.stack_name(...)` and `target.stack_config(env)` instead of hardcoding `aws:region`. Tests added under `tests/deploy/test_program.py`, `tests/deploy/test_aws_dispatch.py` (registry + protocol + config-overlay assertions), `tests/deploy/test_aws_synth.py` (mocked Pulumi via `pulumi.runtime.set_mocks`), `tests/cli/test_deploy_cmd.py`, `tests/plugins/test_plugin_loader.py`, and `tests/plugins/test_late_synth_registration.py` (318 total pass; pulumi-dependent tests gracefully skip when the extras aren't installed). The previous milestone (Phase 4 deploy-build foundation) landed on `claude/continue-redesign-1u5Bv`: a `skaal.deploy` package shipping `build_artefacts(bound, env, app_spec)` (Jinja2 templating into `./.skaal/build/<env>/`), `tags_for(resource, env, fingerprint)` returning a typed `SkaalTags` pydantic model, and the AWS template tree. The Phase 4 dunder sweep, ASGI mount alias deletion, and `skaal plan` rewire landed earlier on `claude/continue-redesign-SbweQ`.

---

## Phase 0 — Branch, version, and rename

- **Status:** code work complete; pending maintainer actions for branch promotion and tag push
- **ADR:** [029](design/029-redesign-foundation-implementation-plan.md)
- **Target alpha tag:** `v0.4.0-alpha.0`

Checklist:

- [ ] 0.1 `v0.4.0-alpha` branch cut from `main` and pushed with branch protection *(deferred — current work lives on `claude/plan-redesign-strategy-A5ixu`; maintainer to promote)*
- [x] 0.2 `pyproject.toml` version bumped to `0.4.0a0` and description rewritten
- [x] 0.2 `CITATION.cff` version bumped to `0.4.0-alpha`
- [x] 0.3 `README.md` hero, tagline, and how-it-works section rewritten (no "Infrastructure as Constraints")
- [x] 0.3 `docs/index.md` updated to the new pitch
- [ ] 0.3 GitHub repo description updated *(manual maintainer action)*
- [x] 0.3 README `## Status` callout added pointing at this tracker
- [x] 0.4 `CLAUDE.md` constraint-thesis sections trimmed; reference to ADR 028 added
- [x] 0.5 `notes/redesign-status.md` created (this file)
- [ ] Tag `v0.4.0-alpha.0` pushed *(maintainer action after branch promotion)*

## Phase 1 — Delete the constraint product

- **Status:** code deletion complete on `claude/plan-redesign-strategy-A5ixu`; archive tags and `v0.4.0-alpha.1` tag are pending maintainer actions
- **ADR:** [029](design/029-redesign-foundation-implementation-plan.md)
- **Target alpha tag:** `v0.4.0-alpha.1`

Checklist:

- [x] 1.1 `skaal/solver/` deleted
- [x] 1.1 `skaal/catalog/` deleted
- [x] 1.1 `catalogs/` deleted
- [x] 1.1 `skaal/types/constraints.py` deleted
- [x] 1.1 `skaal/types/solver.py` deleted
- [x] 1.1 Constraint-type exports removed from `skaal/types/__init__.py`
- [x] 1.1 `skaal/plugins.py` deleted *(the constraint-era plugin system; a new, unrelated entry-point `skaal/plugins.py` layer lands in Phase 4 §4.12 below — naming is reused but the surface is entirely new)*
- [x] 1.1 `skaal/agent.py` deleted *(archive tag `archive/v0.3.x-agent` is a maintainer action — git history preserves the pre-deletion commit)*
- [x] 1.1 `skaal/patterns.py` and `skaal/runtime/engines/` deleted *(archive tag `archive/v0.3.x-patterns` is a maintainer action)*
- [x] 1.1 `skaal/vector.py` deleted; `chroma`/`pgvector` backends deleted *(archive tag `archive/v0.3.x-vector` is a maintainer action)*
- [x] 1.1 `skaal/runtime/mesh_runtime.py`, `skaal/mesh/`, and the top-level `mesh/` Rust crate deleted *(archive tag `archive/v0.3.x-mesh` is a maintainer action)*
- [x] 1.1 Solver/catalog CLI commands deleted (`catalog_cmd.py`, `plan_cmd.py` → stubbed, plus `destroy_cmd.py`, `diff_cmd.py`, `infra_cmd.py`, `stacks_cmd.py` deleted)
- [x] 1.1 Constraint kwargs removed from `@app.storage` and `@app.function` *(the decorator now refuses these kwargs with a standard `TypeError`)*
- [x] 1.1 `@app.handler`, `@app.scale`, `@app.shared` decorators removed
- [x] 1.1 `skaal/components.py` trimmed to `ExternalStorage` + `ExternalQueue` (plus the abstract `ComponentBase` / `ExternalComponent` bases); `APIGateway`, `Route`, `AuthConfig`, `Proxy`, `AppRef`, `ScheduleTrigger`, `ExternalObservability` deleted
- [x] 1.1 `[tool.skaal] extends` and catalog-overlay loaders removed
- [x] 1.2 `@app.compute` renamed to `@app.function`; kwargs trimmed to the resilience-policy subset (`retry`, `circuit_breaker`, `rate_limit`, `bulkhead`)
- [x] 1.3 `skaal/__init__.py` `__all__` re-cut to the Phase 1 subset
- [x] 1.4 `z3-solver`, `langgraph`, catalog entry-points, mesh extra, and vector extras cleaned out of `pyproject.toml`
- [x] 1.4 `[tool.mypy]` `skaal.solver.*` override removed
- [x] 1.5 Shadow test directories deleted (`tests/solver`, `tests/catalog`, `tests/agent`, `tests/mesh`, `tests/deploy`, `tests/runtime`, `tests/api`); surviving tests that reference removed surfaces deleted
- [x] 1.5 Coverage floor temporarily relaxed to 40 in `pyproject.toml` (tracked for restoration in Phase 5)
- [ ] 1.6 CI matrix updated: `maturin`/Rust step removed, tracker-presence check added *(workflows under `.github/workflows/` not yet edited; CI green will be verified once those land)*
- [x] Exit-criterion grep gate passes: `grep -r "Latency\|Durability\|AccessPattern\|Throughput\|Catalog\|@app\.handler\|@app\.scale\|@app\.shared" skaal/` returns zero hits
- [x] `make lint && make typecheck && make test` green (78 tests pass; mypy clean on 63 source files; ruff clean)
- [ ] Tag `v0.4.0-alpha.1` pushed *(maintainer action)*

Phase 1 made several deletions beyond the table above so the remaining tree could compile cleanly without a partial constraint stack:

- `skaal/api.py`, `skaal/plan.py`, and `skaal/deploy/` deleted (Phase 4/7 rewires deploy + the public Python API surface on `InferredPlan` / `BoundPlan`).
- `skaal/runtime/` deleted (Phase 4 rebuilds the local runtime on top of the new bound plan).
- `skaal/cli/migrate/` CLI subgroup deleted (the `skaal/migrate/` engine survives; Phase 6 brings the verbs back).
- `skaal/cli/_utils.py` deleted (its loaders depended on the now-removed `skaal.api` surface).
- `skaal/cli/{plan,build,deploy}_cmd.py` are stubs that exit with a "not yet implemented in 0.4.0-alpha" message so the Phase 1 CI gate (`skaal --help` lists exactly `init`, `run`, `plan`, `build`, `deploy`, `doctor`) is satisfied. The new `doctor` verb prints a minimal toolchain report.
- `SkaalSolverError`, `UnsatisfiableConstraints`, `CatalogError`, and `SkaalPluginError` removed from `skaal.errors` (solver-specific surface).

## Phase 2 — Inference layer (`skaal.inference`)

- **Status:** initial cut landed on `claude/continue-redesign-z5qEy`; follow-ups for `App.mount(path, asgi_app)` reshape, `FunctionRef[P, R]`, `@app.external`, and `Store[T, B]` second-parameter typing are deferred to Phases 2.x / 3 / 4 as scoped in ADR 030
- **ADR:** [030](design/030-inference-layer-implementation-plan.md)
- **Target alpha tag:** `v0.4.0-alpha.2`

Checklist:

- [x] 2.1 `skaal/inference/model.py` — `InferredPlan`, `InferredResource`, `Edge`, `EdgeKind`, `SchemaRef`, `SourceLocation`, `ResourceOverrides`, `ResourceKind` (all frozen pydantic, `extra="forbid"`)
- [x] 2.2 `skaal/inference/walk.py` — `infer(app) -> InferredPlan` walking `Module._storage` / `_functions` / `_jobs` / `_channels` / `_schedules` and submodules
- [x] 2.3 `skaal/inference/fingerprint.py` — 16-char SHA-256 fingerprint, byte-stable across resource/edge reorderings
- [x] 2.4 `skaal/inference/asgi.py` — recogniser that emits an `ASGI_SERVICE` resource when `App.mount_asgi` / `mount_wsgi` has been called
- [x] 2.5 `__skaal_inferred__` populated by `@app.storage`, `@app.function`, `@app.job`, `@app.channel`, `@app.schedule` (additive — legacy dunders survive for Phase 4 rewire)
- [x] 2.6 `App.infer() -> InferredPlan` method and `skaal.inference.infer(app)` function form
- [x] 2.7 `skaal/__init__.py` `__all__` extended with `Edge`, `InferredPlan`, `InferredResource`, `ResourceKind`, `ResourceOverrides`, `SchemaRef`, `SourceLocation`, `infer`
- [x] 2.8 Tests under `tests/inference/` — `test_model.py`, `test_fingerprint.py`, `test_walk.py` (26 new tests; full suite 104 pass)
- [x] `make lint && make typecheck && make test` green
- [ ] 2.x `App.mount(path: str, asgi_app: ASGIApplication)` signature reshape *(deferred — paired with Phase 4 runtime rewire)*
- [ ] 2.x `FunctionRef[P, R]` typed return shape on `@app.function` *(deferred — depends on Phase 4 runtime semantics)*
- [ ] 2.x `@app.external` decorator and `ExternalStorage` / `ExternalQueue` reshape *(deferred — needs Phase 3 binding-layer concept of user-supplied connection)*
- [ ] 2.x `Store[T, B]` / `Relational[T, B]` / `BlobStore[B]` / `Channel[T, B]` second generic defaulting to `Backend` *(deferred — depends on Phase 3 `Backend` token tree)*
- [ ] 2.x `pyright --strict skaal/` green *(deferred — Phase 5 owns the strict-typing pass; ADR 030 §"Out of scope" calls this out)*
- [ ] 2.x Legacy `__skaal_storage__` / `__skaal_function__` / `__skaal_schedule__` / `__skaal_channel__` / `__skaal_job__` dunders deleted *(deferred to Phase 4 — they still feed `schedule.py`'s APScheduler wrapper and the `is_blob_model` / `is_relational_model` predicates)*
- [ ] Tag `v0.4.0-alpha.2` pushed *(maintainer action after the deferred 2.x items above complete)*

## Phase 3 — Binding layer and backend registry (`skaal.binding`)

- **Status:** initial cut landed on `claude/continue-theme-redesign-v16Gc`; follow-ups for `Store[T, B]` second generic, `@app.external`, and `relational-oltp`/`relational-analytics` kind refinement are deferred to Phases 3.x / 4 / 6
- **ADR:** [031](design/031-binding-layer-implementation-plan.md)
- **Target alpha tag:** `v0.4.0-alpha.3`

Checklist:

- [x] 3.1 `skaal/backends/_base.py` — `Backend[NativeClientT]` base class with `name` / `kinds` / `NativeClient` class vars
- [x] 3.2 `skaal/backends/_tokens.py` — 25 `Backend` subclasses (`Sqlite`, `Postgres`, `Redis`, `DynamoDB`, `Firestore`, `S3`, `Gcs`, `FilesystemBlob`, `InProcessChannel`, `RedisChannel`, `Sqs`, `Pubsub`, `Asyncio`, `Lambda`, `CloudRun`, `Uvicorn`, `ApigwLambda`, `Apscheduler`, `EventBridgeLambda`, `CloudSchedulerCloudRun`, `SqsLambdaWorker`, `CloudTasksCloudRun`, `DotenvSecret`, `AwsSecretsManager`, `GcpSecretManager`) plus an `ALL_TOKENS` tuple for registry consistency checks
- [x] 3.3 `skaal/binding/model.py` — `Target`, `BackendConfig`, `ResourceOverride`, `Environment`, `LockEntry`, `LockFile`, `BoundResource`, `BoundPlan` (all frozen pydantic, `extra="forbid"`)
- [x] 3.4 `skaal/binding/registry.py` — `BackendCapabilities`, `BackendOptions` (permissive Phase 3 base schema), `BackendEntry`, `REGISTRY` tuple, plus `lookup`, `lookup_token`, `tokens_for` accessors and the import-time `_registry_consistency_check`
- [x] 3.5 `skaal/binding/defaults.py` — `DEFAULTS` `Mapping[ResourceKind, Mapping[Target, type[Backend]]]` wrapped in `MappingProxyType`
- [x] 3.6 `skaal/binding/environment.py` — `load_environments`, `load_environment` reading `skaal.toml`; absent file yields `{"local": Environment(name="local", target=LOCAL)}`
- [x] 3.7 `skaal/binding/lock.py` — `load_lock`, `write_lock` round-tripping the nested `[entries.<env>."<resource_id>"]` TOML form
- [x] 3.8 `skaal/binding/bind.py` — pure `bind(plan, env, lock) -> BoundPlan` with the four-branch type-pin / lock / env-override / defaults priority order, plus the `_validate` target+kind check
- [x] 3.9 `skaal.errors` — `TypePinViolation`, `BackendKindMismatch`, `BackendNotAvailableForTarget`, `UnknownBackendError` added as `SkaalConfigError` subclasses
- [x] 3.10 `skaal/__init__.py` `__all__` extended with `Backend`, `BackendCapabilities`, `BackendConfig`, `BackendEntry`, `BoundPlan`, `BoundResource`, `Environment`, `LockEntry`, `LockFile`, `ResourceOverride`, `Target`, `bind`, `load_environment`, `load_environments`, `load_lock`, `write_lock`
- [x] 3.11 Tests under `tests/binding/` — `test_model.py`, `test_defaults.py`, `test_registry.py`, `test_bind.py`, `test_environment.py`, `test_lock.py` (47 new tests; full suite 151 pass)
- [x] `make lint && uv run mypy skaal && pytest` green (151 tests; mypy clean on 77 source files; ruff clean)
- [x] 3.x `Store[T, B]` / `Relational[B]` / `BlobStore[B]` / `Channel[T, B]` backend generic populating `ResourceOverrides.backend` *(`Store`/`BlobStore`/`Channel` landed in Phase 4 §4.4; `Relational[B]` followed on this branch as a single-generic shape — the class body is the row schema, no companion DTO — sitting on `SQLModel` + `Generic[B]` whose `__class_getitem__` stashes `__skaal_backend_pin__` onto the parametrised class. `SQLModelMetaclass` overwrites `__orig_bases__` on subclasses, so the decorator's `_extract_backend_pin` now reads `__skaal_backend_pin__` (MRO-inherited) ahead of the `__orig_bases__` walk used by the other primitives. ADR 028 §6.5 and the implementation ADRs 030 / 031 / 032 were swept to the single-generic form in the follow-up commit.)*
- [ ] 3.x `@app.external` decorator using `Environment.backends` for user-supplied connections *(deferred — Phase 4)*
- [ ] 3.x `relational-oltp` / `relational-analytics` kind refinement *(deferred — Phase 6 owns the bytecode walker that emits the refinement)*
- [ ] 3.x `pyright --strict skaal/binding/` green *(deferred — Phase 5 owns the global strict-typing pass)*
- [ ] 3.x Per-backend public import paths (`from skaal.backends.redis import Redis`) re-exporting from `_tokens.py` *(deferred — Phase 4, alongside the decorator rewire that consumes them)*
- [ ] Tag `v0.4.0-alpha.3` pushed *(maintainer action after the deferred 3.x items above complete)*

## Phase 4 — Runtime/deploy on `BoundPlan`

- **Status:** foundations landed on `claude/continue-redesign-lcaT5` (§4.3, §4.4 partial, §4.5, §4.6, §4.7) and `claude/continue-redesign-0ypyZ` (§4.1, §4.8 partial — `skaal run`). The legacy-dunder sweep (§4.9), `App.mount` alias deletion (§4.6), `skaal plan` rewire (§4.8 partial), and examples mount sweep (§4.11 partial) landed on `claude/continue-redesign-SbweQ`. The deploy-build foundation (§4.2 templating half, §4.8 `skaal build`) landed on `claude/continue-redesign-1u5Bv`. The Pulumi-program synth half of §4.2 (`pulumi_program_for`, per-backend AWS synth modules), `skaal deploy` rewire (§4.8 remainder), the structural refactor that introduced the `DeployTarget` Protocol + typed `AwsConfig`, and the plugin architecture (§4.12 — `skaal.plugins` entry-point layer extending both the deploy and binding registries) all landed on `claude/continue-redesign-typed-vars-VHYzp`. The full examples sweep (§4.11 — type-pinned `Cache(Store[Session, Redis])` in `examples/05_task_dashboard`) and the end-to-end `skaal deploy --env prod` smoke against `examples/todo_api` / `examples/counter` against real AWS are still pending — see the Phase 4 checklist below.
- **ADR:** [032](design/032-runtime-deploy-on-bound-plan-implementation-plan.md)
- **Target alpha tag:** `v0.4.0-alpha.4`

Checklist:

- [x] 4.1 `skaal/runtime/` rebuilt on `BoundPlan`: `LocalRuntime.from_bound_plan(bound, app).serve(host, port)`, `dispatch.LOCAL_DISPATCH` keyed by every `ResourceKind`, `wrap_resilience(...)` middleware chain, and adapters for `STORE` (sqlite/redis), `FUNCTION` (resilience-wrapped HTTP routes), `ASGI_SERVICE` (Starlette mounts), `SECRET` (dotenv hydration), `RELATIONAL` (sqlite), `BLOB` (filesystem), `CHANNEL` (in-process pass-through), `SCHEDULE` (APScheduler), and `JOB` (asyncio queue + worker)
- [x] 4.2 `skaal/deploy/` rebuilt with a `DeployTarget` Protocol + `register_target` / `get_target` registry; per-target packages register at import time and expose synth dispatch, stack naming, stack-config, optional-extras, and typed config loading. AWS synth modules (`dynamodb`, `s3`, `secrets`, `postgres`, `redis`, `sqs`, `lambda_fn`, `apigw_lambda`, `eventbridge`, `sqs_worker`) each declare `SPEC: SynthSpec` + `synthesize(ctx)`; `AwsConfig` aggregates typed pydantic configs (`AwsLambdaConfig`, `DynamoDBConfig`, `PostgresConfig`, `RedisConfig`, `S3Config`, `SqsConfig`, `SecretsConfig`, `IamConfig`, `EcrConfig`, `ApiGatewayConfig`, `EventBridgeConfig`) overridable via ``[env.<name>.backends.aws.options.<section>]`` in `skaal.toml`. `pulumi_program_for(bound, env, build_dir)` returns a typed `PulumiProgram` callable, `build_artefacts(...)` and `tags_for(...)` helpers, generic `SynthContext[ConfigT]` / `SynthResult` shapes
- [x] 4.2 Jinja2 templates under `skaal/deploy/templates/aws/` (`Dockerfile.j2`, `handler.py.j2`, `bootstrap.py.j2`, `pyproject.toml.j2` — the Dockerfile installs deps via `uv pip install -r pyproject.toml`)
- [x] 4.3 `BoundPlan.app_fingerprint` + `BoundPlan.bound_fingerprint` fields added; `BoundResource.external` flag added; `bind()` amended to populate both (Phase 3 extension landed in this phase)
- [x] 4.4 Decorator rewire: `Store[T, B]` / `Relational[B]` / `BlobStore[B]` / `Channel[T, B]` backend generic flows into `ResourceOverrides.backend`. `Relational[B]` landed after the other primitives as a single-generic shape — `SQLModelMetaclass` strips `__orig_bases__` from subclasses, so the `Relational` base captures the backend token in `__class_getitem__` (`__skaal_backend_pin__` on the parametrised class, inherited via MRO) and `_extract_backend_pin` reads `__skaal_backend_pin__` ahead of the existing `__orig_bases__` walk. The class body is the row schema; the row-DTO `T` from ADR 028 §6.5.1's two-generic example was dropped to avoid duplicating field declarations.
- [x] 4.4 `@app.external(name=...)` decorator added, requiring a type-pinned second generic
- [x] 4.5 Per-backend public import paths (`from skaal.backends.redis import Redis`) — 25 thin re-export modules (24 new + `RedisChannel` re-exported alongside the existing `RedisStreamChannel` impl)
- [x] 4.6 `App.mount(path: str, asgi_app: ASGIApplication)` is now the canonical surface; `mount_asgi` / `mount_wsgi` deleted along with the `_asgi_app` / `_wsgi_app` recogniser branch; WSGI users wrap with `WSGIMiddleware` at the call site. The inference recogniser walks `app._asgi_path_mounts` only.
- [x] 4.7 `FunctionRef[P, R]` typed return shape added; the decorator now carries `__skaal_inferred__` directly on the ref so consumers no longer rely on attribute forwarding for the inference contract.
- [x] 4.8 `skaal run`, `skaal plan <module:attr>`, `skaal build`, and `skaal deploy` are wired against `infer → bind`; `skaal deploy` drives `pulumi.automation.create_or_select_stack(...).up(...)` against `pulumi_program_for(...)` and writes pinned bindings into `skaal.lock` on success (the plan-as-diff form is Phase 6)
- [x] 4.9 Legacy dunder deletion: every read and write of `__skaal_storage__`, `__skaal_function__`, `__skaal_schedule__`, `__skaal_channel__`, `__skaal_job__`, `__skaal_secrets__` removed from `skaal/`; resilience policies and schedule triggers ride on `ResourceOverrides.resilience` / `.trigger` via `skaal.inference.runtime_meta` encode/decode helpers; `skaal.schedule.create_async_scheduler` (the last legacy reader) deleted. A `tests/typing/test_legacy_dunders_gone.py` grep gate prevents reintroduction.
- [x] 4.10 Tests for the Phase 4 foundations: `tests/decorators/test_backend_pin.py`, `tests/decorators/test_external.py`, `tests/decorators/test_function_ref.py`, `tests/inference/test_mount.py`, `tests/binding/test_phase4_extensions.py`, `tests/backends/test_token_reexports.py`, `tests/runtime/test_dispatch.py`, `tests/runtime/test_local_runtime.py`, `tests/runtime/test_middleware.py`, `tests/cli/test_plan_cmd.py`, `tests/cli/test_build_cmd.py`, `tests/cli/test_load_types.py`, `tests/cli/test_deploy_cmd.py`, `tests/deploy/test_build.py`, `tests/deploy/test_models.py`, `tests/deploy/test_tags.py`, `tests/deploy/test_program.py`, `tests/deploy/test_aws_dispatch.py`, `tests/deploy/test_aws_synth.py` (synth tests are gated on `pulumi.runtime.set_mocks`), `tests/plugins/test_plugin_loader.py`, `tests/plugins/test_late_synth_registration.py`, `tests/typing/test_legacy_dunders_gone.py` (full suite 318 pass; pulumi-dependent tests skip when the `deploy,aws` extras aren't installed)
- [x] 4.11 Examples switched from `mount_asgi` / `mount_wsgi` to `app.mount("/", asgi_app)` (`session_cache`, `02_todo_api`, `03_dash_app`, `05_task_dashboard`, `06_fastapi_streaming`, `07_file_upload_api`); legacy constraint kwargs (`read_latency`, `durability`, `access_pattern`, `retention`) stripped from `examples/01_hello_world`, `examples/07_file_upload_api`, `examples/session_cache`, and `examples/team_directory`; the type-pinned `Store[T, Redis]` demonstration landed in `examples/session_cache.py` (originally scoped to `05_task_dashboard`, but that example still depends on Phase 1-deleted surfaces — `VectorStore`, `Agent`, `EventLog`, `Saga`, `Durability`, `Persistent`, `Scale`, `ScaleStrategy`, `@handler` — and is left for the Phase 7 examples/docs rewrite). `Sessions` and `Tokens` declare `Store[SessionRecord, Redis]` / `Store[TokenRecord, Redis]`, which flows through inference as `ResourceOverrides.backend == "redis"` and survives binding against both `local` and `aws` targets (`pinned=True` on the `BoundResource`). Class-level TTL is set via the `__skaal_default_ttl_seconds__` ClassVar (no decorator kwarg) and per-call overrides on `Sessions.set(..., ttl="45m")` still work. The broken `03_dash_app`, `05_task_dashboard`, `04_mesh_counter`, and `mesh_counter` examples are still on disk untouched.
- [x] 4.12 Plugin architecture (`skaal.plugins`) — beyond ADR 032's original Phase 4 scope, anticipates the third-party `BackendProtocol` deferred to v0.5 in ADR 028 §10.5. `SkaalPlugin` runtime-checkable Protocol exposed via the `[project.entry-points."skaal.plugins"]` entry-point group; `PluginRegistry` contribution surface (`add_target`, `add_synth`, `add_backend`); `load_plugins()` walks entry points lazily on first `get_target(...)` / `lookup(...)` / `tokens_for(...)`. `BaseDeployTarget.register_synth(synth)` permits late synth registration; `skaal.binding.registry.register_backend(entry)` permits late `BackendEntry` registration with idempotent same-token re-add and clear conflict-on-name semantics. Broken plugins log a warning and are skipped; Skaal's own boot never breaks on a third-party failure.
- [x] 4.13 Synth class hierarchy — each synth contribution is now a `SynthModule[ConfigT]` subclass (generic over the target's `TargetConfig`) declaring `SPEC: ClassVar[SynthSpec]` and implementing `synthesize(ctx)`. `BaseDeployTarget.from_classes(...)` instantiates each class once and assembles the dispatch. The four Lambda-shaped AWS synths (`PlainLambdaSynth`, `ApigwLambdaSynth`, `EventBridgeLambdaSynth`, `SqsWorkerSynth`) inherit from `LambdaSynth`, an abstract base that owns the ECR + image + IAM + log group + function scaffold; subclasses override `_event_source(ctx, scaffold)` (and `_timeout_s` / `_memory_mb` when needed) instead of re-implementing the boilerplate. `PluginRegistry.add_synth(target, cls_or_instance)` accepts either a `SynthModule` subclass or an instance, so third-party plugins inherit the same contract.
- [x] Exit-criterion grep gate: `grep -r "__skaal_storage__\|__skaal_function__\|__skaal_schedule__\|__skaal_channel__\|__skaal_job__" skaal/` returns zero hits
- [x] `skaal run` boots `examples/todo_api` against a `local` environment and serves HTTP on `localhost:8000` — verified end-to-end: `POST /todos`, `GET /todos`, `GET /todos/{id}`, `POST /todos/{id}/comments`, `GET /todos/{id}/comments`, and `DELETE /todos/{id}` all return the expected JSON, with the SQLite-backed KV store and the SQLAlchemy-backed relational session both persisting state inside one run. `examples/counter` is also runnable. Two bugs fixed along the way: the indirect `examples/todo_api.py` loader now registers the spec module in `sys.modules` (pydantic forward-reference resolution requires it), and the `RELATIONAL` adapter now calls `wire_relational_model(target, backend)` so `open_relational_session(Comments)` finds the wired backend instead of raising `NotImplementedError`.
- [ ] `skaal deploy --env prod` (target `aws`) provisions resources for `examples/todo_api` and `examples/counter` with `skaal:*` tags
- [x] `uv run ruff check && uv run mypy skaal && uv run pytest` green (331 tests; mypy clean on 139 source files; ruff clean)
- [ ] Tag `v0.4.0-alpha.4` pushed *(maintainer action)*

## Phase 5 — Typing contract and `skaal stubs`

- **Status:** not started
- **ADR:** planned 033
- **Target alpha tag:** `v0.4.0-alpha.5`

Checklist: TBD when ADR 033 lands. Includes the restoration of the coverage floor from 40 back to 60.

## Phase 6 — `skaal plan` diff, `map`, `where`, `trace`, PR-comment action

- **Status:** not started
- **ADR:** planned 034
- **Target alpha tag:** `v0.4.0-alpha.6`

Checklist: TBD when ADR 034 lands.

## Phase 7 — Docs, examples, migration guide; cut `v0.4.0`

- **Status:** not started
- **ADR:** planned 035
- **Target release tag:** `v0.4.0` (on `main`, after squash-merge from `v0.4.0-alpha`)

Checklist: TBD when ADR 035 lands.

---

## Archive tags

These tags preserve code removed during Phase 1 so it can be resurrected if a future contributor champions it. Pushing the tags is a maintainer action — until then, the pre-deletion commit on `claude/plan-redesign-strategy-A5ixu` is reachable via git history.

- [ ] `archive/v0.3.x-agent` — last commit of `skaal/agent.py`
- [ ] `archive/v0.3.x-patterns` — last commit of `skaal/patterns.py` and `skaal/runtime/engines/`
- [ ] `archive/v0.3.x-vector` — last commit of `skaal/vector.py`
- [ ] `archive/v0.3.x-mesh` — last commit of `skaal/runtime/mesh_runtime.py` and the `mesh/` Rust crate

## Success criteria for `v0.4.0` (from ADR 028 §12)

The redesign is complete when all nine of these are simultaneously true. Tick as each becomes verifiable on the `v0.4.0-alpha` branch.

- [ ] `skaal init && skaal run` requires zero arguments and zero config edits
- [ ] `skaal plan --env prod` produces a deterministic diff readable in under 30 seconds
- [ ] `skaal deploy --env prod` writes `skaal.lock` and the next `skaal plan` is empty unless code changed
- [ ] A `Store[T]` in one module is importable, typed, and usable from another module with no codegen step
- [ ] `pyright --strict` green on `skaal/`, `examples/`, `tests/typing/`; every §6.13.3 `reveal_type` assertion passes
- [ ] `class Sales(Relational[Sale, BigQuery])` plus `await Sales.native()` resolves to `google.cloud.bigquery.Client` in Pylance, runs against real BigQuery locally per `env.local.backends.bigquery`, and a conflicting override fails with `TypePinViolation` at config-load
- [ ] Opening a PR posts an infra-diff comment automatically
- [ ] The word "constraint" appears nowhere in user-facing docs, CLI help, or decorator signatures
- [ ] `examples/todo_api` walkthrough deploys to AWS in under 5 minutes from a fresh checkout
