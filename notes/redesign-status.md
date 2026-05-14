# Redesign status (ADR 028)

This file is the canonical answer to "where are we in the redesign?" It carries state only — design decisions live in the implementation ADRs (029, 030, …). See [ADR 029](design/029-redesign-foundation-implementation-plan.md) for the update protocol.

**Current alpha:** `v0.4.0a0` declared in `pyproject.toml`; no alpha tag pushed yet.
**Branch:** `claude/plan-redesign-strategy-A5ixu` (de-facto `v0.4.0-alpha` working branch). Promotion/rename to `v0.4.0-alpha` on `origin` is a maintainer action.
**Last updated:** 2026-05-13 — Phase 2 inference layer landed on `claude/continue-redesign-z5qEy`.

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
- [x] 1.1 `skaal/plugins.py` deleted
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

- **Status:** not started
- **ADR:** planned 031
- **Target alpha tag:** `v0.4.0-alpha.3`

Checklist: TBD when ADR 031 lands.

## Phase 4 — Runtime/deploy on `BoundPlan`

- **Status:** not started
- **ADR:** planned 032
- **Target alpha tag:** `v0.4.0-alpha.4`

Checklist: TBD when ADR 032 lands.

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
