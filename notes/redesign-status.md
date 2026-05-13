# Redesign status (ADR 028)

This file is the canonical answer to "where are we in the redesign?" It carries state only — design decisions live in the implementation ADRs (029, 030, …). See [ADR 029](design/029-redesign-foundation-implementation-plan.md) for the update protocol.

**Current alpha:** `v0.4.0a0` declared in `pyproject.toml`; no alpha tag pushed yet.
**Branch:** `claude/plan-redesign-strategy-A5ixu` (de-facto `v0.4.0-alpha` working branch). Promotion/rename to `v0.4.0-alpha` on `origin` is a maintainer action.
**Last updated:** 2026-05-13

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

- **Status:** not started
- **ADR:** [029](design/029-redesign-foundation-implementation-plan.md)
- **Target alpha tag:** `v0.4.0-alpha.1`

Checklist:

- [ ] 1.1 `skaal/solver/` deleted
- [ ] 1.1 `skaal/catalog/` deleted
- [ ] 1.1 `catalogs/` deleted
- [ ] 1.1 `skaal/types/constraints.py` deleted
- [ ] 1.1 `skaal/types/solver.py` deleted
- [ ] 1.1 Constraint-type exports removed from `skaal/types/__init__.py`
- [ ] 1.1 `skaal/plugins.py` deleted
- [ ] 1.1 `skaal/agent.py` archived to `archive/v0.3.x-agent` then deleted
- [ ] 1.1 `skaal/patterns.py` and `skaal/runtime/engines/` archived to `archive/v0.3.x-patterns` then deleted
- [ ] 1.1 `skaal/vector.py` archived to `archive/v0.3.x-vector` then deleted
- [ ] 1.1 `skaal/runtime/mesh_runtime.py` and `mesh/` crate archived to `archive/v0.3.x-mesh` then deleted
- [ ] 1.1 `skaal/cli/commands/catalog*.py`, `solver*.py`, `explain.py` deleted
- [ ] 1.1 Constraint kwargs removed from `@app.storage` and `@app.compute`; raise `TypeError` with migration hint
- [ ] 1.1 `@app.handler`, `@app.scale`, `@app.shared` decorators removed
- [ ] 1.1 `skaal/components.py` user-facing classes removed (`APIGateway`, `Route`, `AuthConfig`, `Proxy`, `AppRef`, `ScheduleTrigger`, `ExternalObservability`)
- [ ] 1.1 `[tool.skaal] extends` and catalog-overlay loaders removed
- [ ] 1.2 `@app.compute` renamed to `@app.function`; kwargs trimmed to §6.5 override vocabulary
- [ ] 1.3 `skaal/__init__.py` `__all__` re-cut to the Phase 1 subset
- [ ] 1.4 `z3-solver`, catalog entry-points, vector dependencies cleaned out of `pyproject.toml`
- [ ] 1.4 `[tool.mypy]` `skaal.solver.*` override removed
- [ ] 1.5 Shadow test directories deleted; surviving tests that reference removed surfaces deleted
- [ ] 1.5 Coverage floor temporarily relaxed to 40 in `pyproject.toml` (tracked for restoration in Phase 5)
- [ ] 1.6 CI matrix updated: `maturin`/Rust step removed, tracker-presence check added
- [ ] Exit-criterion grep gate passes: `grep -r "Constraint\|Latency\|Durability\|AccessPattern\|Throughput\|Catalog\|@app\.handler\|@app\.scale\|@app\.shared" skaal/` returns zero hits outside ADR-referencing comments
- [ ] `make lint && make typecheck && make test` green
- [ ] Tag `v0.4.0-alpha.1` pushed

## Phase 2 — Inference layer (`skaal.inference`)

- **Status:** not started
- **ADR:** planned 030
- **Target alpha tag:** `v0.4.0-alpha.2`

Checklist: TBD when ADR 030 lands.

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

These tags preserve code removed during Phase 1 so it can be resurrected if a future contributor champions it. Created in the same release as `v0.4.0-alpha.1`.

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
