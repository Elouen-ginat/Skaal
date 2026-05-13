# ADR 029 — Redesign Foundation: Branching Strategy, Progress Tracking, and Phase 0/1 Implementation Plan

**Status:** Proposed
**Date:** 2026-05-13
**Related:** [ADR 028](028-code-first-infra-redesign.md) (the redesign), [ADR 019](019-simplification-report.md)
**Supersedes execution detail in:** ADR 028 §9 phases 0 and 1 (this ADR is the operational plan; ADR 028 remains the product definition)

---

## Goal

Land the first implementation pass of the [ADR 028](028-code-first-infra-redesign.md) redesign and establish the working model for every implementation ADR that follows it.

This ADR answers three operational questions ADR 028 deliberately did not:

1. **Where does the new code live?** In-place on a long-lived release branch, or in a parallel `skaal2/` tree?
2. **How is progress measured across an estimated ~6.5 engineer-weeks split into eight phases?**
3. **What is the concrete file-by-file shape of Phase 0 (branch, rename) and Phase 1 (delete the constraint product)?**

It then ships Phases 0 and 1 to their stated exit criteria. The inference, binding, runtime, typing, and diff layers (Phases 2–7 of ADR 028) each get their own implementation ADR; this one is the foundation they all assume.

## Why this is the first implementation ADR

ADR 028 is the product decision; it is intentionally silent on _how_ a single contributor walks from `0.3.1` to `0.4.0` without leaving the tree in a half-redesigned state for weeks at a time. Three things must be decided before any feature work starts, because every later phase consumes them:

1. **The branching model.** If Phases 2–7 land on `main` directly, every intermediate commit ships a broken or hybrid product. If they land on a long-lived branch, the rebase/merge discipline has to be settled up front.
2. **The progress artifact.** Eight phases with multi-criterion exits cannot be tracked in commit messages or PR titles. The team needs a single file to point at when asked "where are we?"
3. **The demolition surface.** Phase 1 deletes roughly a quarter of the package. Done piecemeal across PRs it leaves the tree compiling-but-incoherent for days; done as one atomic pass it is reviewable.

Settling these now also forces the rejected alternative (a parallel `skaal2/` tree) to be evaluated against the corrosion argument in ADR 028 §2 before anyone is tempted to take it.

## Scope

In scope:

- The branching model for the entire redesign.
- The progress-tracking artifact and its update protocol.
- Phase 0 of ADR 028 §9: branch cut, version bump, marketing rename, `CLAUDE.md` updates.
- Phase 1 of ADR 028 §9: deletion of the constraint product (`skaal.solver`, `skaal.catalog`, `catalogs/`, constraint primitives in `skaal.types`, constraint kwargs on decorators, the agent/patterns/vector/mesh quarantine).
- The CI posture during demolition (which jobs stay green, which are temporarily relaxed, and on what schedule they return).

Out of scope (each is its own implementation ADR):

- Building `skaal.inference` (Phase 2 — future ADR 030).
- Building `skaal.binding` and the backend registry (Phase 3 — future ADR 031).
- Rewiring `skaal.runtime` and `skaal.deploy` onto `BoundPlan` (Phase 4 — future ADR 032).
- Typing contract enforcement and `skaal stubs` (Phase 5 — future ADR 033).
- `skaal plan` diff, `skaal map`, `skaal where`, PR-comment Action (Phase 6 — future ADR 034).
- Docs, examples, migration guide (Phase 7 — future ADR 035).
- Relicensing (out of scope per ADR 028 §10; its own ADR when ready).

This ADR's exit is "the tree compiles with the constraint product gone, the `v0.4.0-alpha` branch is live, and the tracker is wired up." It is not "the redesign is feature-complete."

## Decision 1 — In-place rewrite on a long-lived `v0.4.0-alpha` branch

**The redesign edits the existing `skaal/` package on a long-lived `v0.4.0-alpha` branch cut from `main`. No parallel `skaal2/` or `skaal_v2/` tree is created. No `from skaal.v1 import …` shim is shipped.**

Rationale:

1. **ADR 028 §2 is explicit: the two theses are corrosive.** The constraint vocabulary (`Latency`, `Durability`, `AccessPattern`, …) re-imports the parallel-reality problem the redesign exists to delete. A side folder would force every contributor to mentally hold both products, which is the exact state the redesign rejects.
2. **Alpha posture.** The project is `0.3.1` with no compatibility guarantee. ADR 028 commits to no shims (§1 "Breaking"). A parallel tree would be a shim by another name, only larger.
3. **One `__init__.py` `__all__` to maintain.** A parallel tree forks the public-surface contract, doubling the surface the typing tests in Phase 5 have to police. With one tree, `skaal/__init__.py` always reflects the only truth.
4. **Git history stays linear and bisectable.** Deletions are easier to read in a `git log -- skaal/solver/` than a "moved to skaal_v1/" rename diff.
5. **Pre-commit, mypy, ruff, and CI keep working without per-tree configuration.** Mypy's stricter overrides for `skaal.types.*` and `skaal.solver.*` in `pyproject.toml` need updating either way; with a parallel tree they would have to be duplicated.

### Alternatives considered and rejected

- **Parallel `skaal2/` tree merged into `skaal/` at 0.4.0.** Rejected. Doubles the surface for the duration of the redesign; tempts "keep the old around just in case"; the merge event becomes a single oversized PR no reviewer can usefully read.
- **Feature-flagged hybrid (`SKAAL_NEW=1` flips the import surface).** Rejected. The constraint vocabulary appears in decorator signatures and type names — a flag cannot toggle that without rewriting every user-facing decorator twice.
- **Land each phase as a PR into `main`.** Rejected. Phases 2 and 3 introduce `InferredPlan`/`BoundPlan` without consumers (the runtime and deploy layers still expect `PlanFile`). Landing them on `main` ships a hybrid product for weeks. The release-branch model lets each phase be reviewable in isolation while the public surface stays coherent at every tagged alpha.
- **Two long-lived branches (one per cloud target).** Rejected. ADR 028 §10 already decides AWS first, GCP follows in a 0.4.x point release. Splitting branches splits the test matrix too.

### Branch lifecycle

| Event | Action |
|---|---|
| Phase 0 begins | `git checkout -b v0.4.0-alpha main` and push. `main` continues to receive `0.3.x` bugfixes only. |
| Each phase exits | Tag `v0.4.0-alpha.N` on the branch (N = phase index, starting at `v0.4.0-alpha.1` after Phase 1). Publish to TestPyPI, not PyPI. |
| `main` receives a bugfix | Cherry-pick into `v0.4.0-alpha` only if the affected surface still exists post-Phase-1. Otherwise discard. |
| All phases complete | Squash-merge `v0.4.0-alpha` into `main` as a single "feat: redesign to code-first infra (ADR 028)" commit, tag `v0.4.0`, publish to PyPI. The branch is deleted after the merge tag is signed. |

This keeps `main` shippable for the (rare) `0.3.x` patch release while the redesign is in flight, and avoids any window during which both products are simultaneously installable.

## Decision 2 — Progress is tracked in `notes/redesign-status.md`

A single living Markdown file at `notes/redesign-status.md` is the canonical answer to "where are we in the redesign?" It is not an ADR (ADRs are decisions, not state) and not a GitHub Project (the status has to travel with the source tree so a checkout from six months ago still tells the right story).

### Layout

```markdown
# Redesign status (ADR 028)

**Current alpha:** v0.4.0-alpha.1
**Branch:** v0.4.0-alpha
**Last updated:** 2026-05-13

## Phase 0 — Branch, version, and rename
Status: complete (2026-05-13)
ADR: 029
- [x] v0.4.0-alpha branch cut from main
- [x] pyproject.toml description updated
- [x] README hero rewritten
- [x] CLAUDE.md constraint references removed
- [x] CITATION.cff version bumped

## Phase 1 — Delete the constraint product
Status: in progress
ADR: 029
- [x] skaal/solver/ deleted
- [ ] skaal/catalog/ deleted
- [ ] catalogs/ deleted
- ...

## Phase 2 — Inference layer
Status: not started
ADR: (planned) 030
- [ ] ...
```

### Update protocol

- Each implementation ADR owns one or more phase sections. The ADR is the contract; the tracker reflects current state.
- The tracker is updated in the same commit that satisfies an exit-criterion checkbox. CI rejects a phase-completion commit if the tracker still shows the phase as incomplete (see "CI gates" below).
- Every alpha tag bumps the "Current alpha" line. The previous value is preserved in `git log -- notes/redesign-status.md`.
- The tracker carries no design content — only state. Design lives in ADRs.

### Why a file, not a GitHub Project

A Project board would be lost to anyone reading the repo offline, to a fork, or to an LLM agent loading the tree without API access. The tracker is the kind of thing that has to travel inside the source — same argument as the ADRs themselves.

## Decision 3 — Demolition is one atomic Phase 1, not piecemeal

Phase 1 (the constraint deletions) lands as **one PR** against the `v0.4.0-alpha` branch, not as a sequence of "remove `skaal.solver`", "remove `skaal.catalog`", "remove constraint kwargs" PRs. Rationale:

1. The deletions are coupled. Removing `skaal/solver/` without removing the constraint kwargs that feed it leaves dangling references; removing the kwargs without removing `skaal/catalog/` leaves a catalog with no readers. The minimum coherent state is "all of them gone."
2. The intermediate states are not useful to anyone. There is no scenario where a user or contributor wants `skaal.solver` deleted but `Latency`/`Durability` still importable.
3. One PR is one review. A reviewer holds the deletion surface in their head once. Six PRs force the reviewer to context-switch six times.
4. The PR is mechanical and grep-driven (see "Phase 1 implementation" below). Mechanical work is exactly what reviews well in a single large diff.

Phases 2 onward are different in character — they add surface, and additions are best reviewed in slices. Phase 1's monolithic PR is a one-off.

## Phase 0 implementation

### 0.1 — Cut the release branch

```bash
git checkout main
git pull --ff-only
git checkout -b v0.4.0-alpha
git push -u origin v0.4.0-alpha
```

Branch protection on `v0.4.0-alpha` mirrors `main`: required CI, signed commits, no force-push.

### 0.2 — Version bump

`pyproject.toml`:

- `version = "0.4.0a0"` (PEP 440 prerelease form; bumped to `a1`, `a2`, … as each phase exits).
- `description = "A Python framework where the application code is the infrastructure declaration."` (drops "Infrastructure as Constraints").

`CITATION.cff` `version:` field bumped to `0.4.0-alpha`.

### 0.3 — Marketing rename

The pitch in ADR 028 §13 replaces every "Infrastructure as Constraints" usage in:

- `README.md` (hero, tagline, the "How it works" paragraph that walks through Z3).
- `docs/index.md` (front-matter and first three sections).
- `docs/about.md` if it carries the constraint pitch.
- The GitHub repo description (manual step, recorded in the tracker as `[ ] Update GitHub repo description`).

Constraint walkthroughs in `README.md` that show `Latency`, `Durability`, etc., are deleted, not rewritten — Phase 7 owns the replacement narrative. For the duration of Phases 1–6 the README has a `## Status` callout pointing at the redesign tracker.

### 0.4 — `CLAUDE.md` update

The project memory still describes the constraint-solver thesis (see the "Constraint layer / Solver layer / …" section). Phase 0 trims it to:

- Drop the "Constraint declaration" and "Solver pipeline" subsections.
- Replace with a one-paragraph reference to ADR 028 and a "redesign in progress, see `notes/redesign-status.md`" note.
- Leave the development-tools, testing, CI, and conventions sections intact.

Phase 7 rewrites `CLAUDE.md` in full once the new architecture is in place.

### 0.5 — Create `notes/redesign-status.md`

Initial contents listed under Decision 2. All phases except Phase 0 start as `not started` with empty checklists; Phase 0's own checklist is filled in as 0.1–0.5 land.

### Phase 0 exit criteria

1. `v0.4.0-alpha` branch exists on origin with branch protection enabled.
2. `pyproject.toml` reports `0.4.0a0` and the new description.
3. `README.md` no longer contains the string `Infrastructure as Constraints`.
4. `CLAUDE.md` no longer describes the constraint thesis.
5. `notes/redesign-status.md` exists and marks Phase 0 as complete.
6. `make lint && make typecheck && make test` are still green on `v0.4.0-alpha` (nothing has been deleted yet).
7. The release tag `v0.4.0-alpha.0` is pushed.

## Phase 1 implementation

### 1.1 — The deletion table

Every entry here corresponds to a single `git rm -r` (or directory delete) on the `v0.4.0-alpha` branch. Each row identifies the surface, the rationale in ADR 028, and the post-delete check.

| Path | ADR 028 §4.1 reference | Post-delete check |
|---|---|---|
| `skaal/solver/` (12 modules) | "Delete." | `grep -r "from skaal.solver" skaal/ tests/ examples/` returns 0. |
| `skaal/catalog/` (loader, models, registry, data) | "Delete. The catalog concept ends." | `grep -r "from skaal.catalog" skaal/ tests/ examples/` returns 0. |
| `catalogs/` (`local.toml`, `aws.toml`, `gcp.toml`) | "Delete." | `ls catalogs/` returns "No such file or directory." |
| `skaal/types/constraints.py` | "Delete." | `grep -r "from skaal.types.constraints" skaal/ tests/ examples/` returns 0. |
| `skaal/types/solver.py` | "Delete." | `grep -r "from skaal.types.solver" skaal/ tests/ examples/` returns 0. |
| Constraint-type exports in `skaal/types/__init__.py` (`Latency`, `Durability`, `AccessPattern`, `Throughput`, `Consistency`, throughput tier constants, cost weights) | "Delete." | `grep -RE "\\b(Latency\\|Durability\\|AccessPattern\\|Throughput\\|Consistency)\\b" skaal/ tests/ examples/` returns 0 outside ADR/changelog references. |
| `skaal/plugins.py` | "Delete." | `grep -r "from skaal.plugins" skaal/ tests/ examples/` returns 0. |
| `skaal/agent.py` | "Move to skaal-contrib or delete." | Archived to `archive/v0.3.x-agent` branch, then deleted from `v0.4.0-alpha`. |
| `skaal/patterns.py` | Same. | Archived to `archive/v0.3.x-patterns`, then deleted. |
| `skaal/runtime/engines/` (projection, saga, outbox) | Same. | Archived to `archive/v0.3.x-patterns`, then deleted. |
| `skaal/vector.py` | "Remove as core." | Archived to `archive/v0.3.x-vector`, then deleted. |
| `skaal/runtime/mesh_runtime.py` | "Quarantine behind an off-by-default feature flag." | Archived to `archive/v0.3.x-mesh`, then deleted from `v0.4.0-alpha`. |
| `mesh/` (Rust crate) | Same. | Archived to `archive/v0.3.x-mesh`. The build is removed from `maturin` config; `pyproject.toml`'s `build-system` reverts to pure-Python. |
| `skaal/cli/commands/catalog*.py` | "Delete." | `grep -r "catalog" skaal/cli/` returns 0 outside dead-code comments slated for removal in 1.3. |
| `skaal/cli/commands/solver*.py`, `skaal/cli/commands/explain.py` | "Delete." | Same. |
| Constraint kwargs on `@app.storage`, `@app.compute` (`latency=`, `durability=`, `access_pattern=`, `throughput=`, `consistency=`, `read_latency=`, `write_latency=`, `freshness=`, `cost_tier=`) | "Removed at the parser level." | The decorator raises `TypeError` listing the removed kwargs with a one-line "see ADR 028 §6.5 for the new override vocabulary" hint. Test in `tests/decorators/test_removed_kwargs.py`. |
| `@app.handler`, `@app.scale`, `@app.shared` decorators (and `__skaal_handler__` / `__skaal_scale__` / `__skaal_shared__` metadata attributes) | "Delete." | The names disappear from `skaal/decorators.py`; importing them raises `ImportError`. |
| `skaal/components.py` user-facing classes: `APIGateway`, `Route`, `AuthConfig`, `Proxy`, `AppRef`, `ScheduleTrigger`, `ExternalObservability` | "Replace. The new surface infers them." | `grep -r "APIGateway\\|Route\\|AuthConfig" skaal/ tests/ examples/` returns 0. `ExternalStorage` and `ExternalQueue` survive intact for Phase 2 to reshape. |
| `[tool.skaal] extends`, catalog-overlay config loaders | "Delete." | The `extends` key is removed from `skaal/settings.py` and `pyproject.toml`. |

### 1.2 — Decorator rename

`@app.compute` → `@app.function` in this PR, with the kwargs trimmed to the §6.5 override vocabulary plus the per-function kwargs ADR 028 §6.4.2 enumerates (`memory_mb`, `timeout_s`, `min_concurrency`, `max_concurrency`, `auth`). The full typed `FunctionRef[P, R]` return shape is Phase 2's responsibility; Phase 1 just renames and trims.

Renaming `compute` → `function` is grep-driven across `skaal/`, `tests/`, and `examples/`. The renamed surface is added to `skaal/__init__.py` `__all__`; the old name is **not** kept as an alias (no backcompat).

### 1.3 — `skaal/__init__.py` re-cut

The `__all__` list shrinks to:

```python
__all__ = [
    # Composition
    "App", "Module", "ModuleExport",
    # Typed primitives
    "Store", "BlobStore", "Channel",
    # Will be reshaped in Phase 2 but the names survive
    "function",  # the @app.function decorator
    "Cron", "Every", "Schedule", "ScheduleContext",
    "Secret", "SecretRegistry",
    "ensure_relational_schema", "open_relational_session",
    "sync_run",
    # Adapters (reshaped in Phase 2)
    "external",
]
```

`Relational[T, B]`, `FunctionRef`, backend tokens, and the registry-introspection types arrive in Phases 2–3. Phase 1's `__init__.py` is a strict subset of the eventual surface — anything ADR 028 §8 calls for that does not yet exist is simply absent.

### 1.4 — `pyproject.toml` cleanup

- Drop the `[project.entry-points."skaal.backends"]` and `[project.entry-points."skaal.channels"]` tables. The registry takes over in Phase 3 (ADR 028 §6.12); for Phase 1 the backends in `skaal/backends/` exist but are not yet discoverable.
- Drop `z3-solver` from `[project.dependencies]`.
- Drop `[tool.skaal] extends`-related settings.
- Drop the `[tool.skaal.solver]` section if any.
- Move `langgraph`, `chromadb`, `pgvector`, `psycopg`, `langchain-*` out of `[project.dependencies]` and into the `vector` optional extra (already partially the case — Phase 1 finishes the move).
- Adjust `[tool.mypy]` to drop the stricter override for `skaal.solver.*` (the module no longer exists). Keep the override for `skaal.types.*`; tighten it in Phase 5.

### 1.5 — Test-suite triage

The existing test tree shadows the package structure. After 1.1's deletions, the corresponding `tests/solver/`, `tests/catalog/`, `tests/types/test_constraints.py`, `tests/patterns/`, `tests/vector/`, `tests/agent/`, and `tests/mesh/` directories are deleted in the same PR.

Tests that survive but reference deleted surfaces (e.g., a runtime test that constructs `APIGateway(...)`) are deleted, not patched. Phase 4 owns the runtime rewrite; resurrecting these tests against the new surface is its job, not Phase 1's.

The coverage floor (`fail_under = 60` in `[tool.coverage.report]`) is temporarily relaxed to `40` for the duration of Phases 1–4 and tracked as a known regression in the tracker. Phase 5 restores it to `60` once the typing tests and example-driven coverage refill the lost ground.

### 1.6 — CI gates

For the `v0.4.0-alpha` branch:

- `make lint` must pass.
- `make typecheck` must pass.
- `make test` must pass (against the trimmed suite).
- `make build` (the maturin/Rust step) is removed from the CI matrix — there is no Rust crate any longer.
- The pre-commit hook for `bandit` keeps its existing exclusion list.
- A new CI step verifies that `notes/redesign-status.md` reflects the in-progress phase. Concretely:

  ```bash
  grep -q "^Status: in progress$" notes/redesign-status.md || \
    grep -q "^Status: complete" notes/redesign-status.md
  ```

  Phase-completion commits include the checkbox update in the same patch.

### Phase 1 exit criteria

ADR 028's stated exit criterion is the canonical test:

> `grep -r "Constraint\\|Latency\\|Durability\\|AccessPattern\\|Throughput\\|Catalog\\|@app\\.handler\\|@app\\.scale\\|@app\\.shared" skaal/` returns zero hits outside of comments referencing this ADR.

Beyond that:

1. `make lint && make typecheck && make test` are green on `v0.4.0-alpha`.
2. `skaal --help` runs and lists exactly: `init`, `run`, `plan`, `build`, `deploy`, `doctor` (the verbs that survive Phase 1; `map`, `where`, `trace`, `rebind`, `unbind`, `stubs`, `backends` arrive in their respective later phases).
3. `python -c "import skaal; print(skaal.__all__)"` matches the subset in 1.3.
4. `pyproject.toml` has no `z3-solver`, no catalog entry-points, no `extends`.
5. The release tag `v0.4.0-alpha.1` is pushed.
6. The tracker marks Phase 1 as complete.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| The deletion PR is too large to review. | Phase 1 is mechanical, grep-driven, and accompanied by the deletion table above. The reviewer's job is "does the grep gate pass and is anything in the table missing?" — not "is this code correct?" |
| A user is mid-upgrade from `0.3.0` to `0.3.1` when the redesign lands. | `main` continues to receive `0.3.x` patches until `v0.4.0` is tagged. Pinning a `0.3.x` install picks up no redesign work. |
| The `v0.4.0-alpha` branch goes stale relative to `main`. | Cherry-pick narrowly. Most `main` changes during the redesign should be to surfaces the redesign deletes (the solver), in which case they are no-ops on `v0.4.0-alpha`. Anything else (docs, CI) is mechanical to port. |
| Archive branches (`archive/v0.3.x-mesh`, etc.) get pruned. | Each is tagged in the same release as Phase 1 exits (`v0.4.0-alpha.1`). The tag prevents pruning. The tracker lists every archive tag. |
| A future contributor confuses `v0.4.0-alpha` with `main`. | The merge of `v0.4.0-alpha` into `main` at 0.4.0 deletes the branch immediately after the tag is signed. There is no long-lived "v1" branch after the redesign ships. |
| Coverage regression makes a real bug invisible. | The temporary `40` floor is loud (CI announces it). The tracker carries an explicit checkbox to restore `60` before Phase 5 exits. |

## Non-goals for this ADR

1. Designing the inference layer's pydantic models (ADR 030).
2. Designing the binding layer or the backend registry (ADR 031).
3. Choosing between AWS and GCP first for Phase 4 (already decided in ADR 028 §10: AWS first).
4. The relicensing decision.
5. A migration guide for `0.3.x` users (Phase 7 owns this).
6. Any new feature. Phase 1 is pure deletion.

## What comes next

Once this ADR lands and Phases 0 and 1 are tagged as `v0.4.0-alpha.1`:

1. **ADR 030 — Inference layer implementation plan.** Owns Phase 2 of ADR 028 §9: `skaal.inference` package, the pydantic `InferredPlan` and friends, the `@app.function` rename's full typed shape, and the `__skaal_inferred__` metadata convergence.
2. **ADR 031 — Binding layer and backend registry implementation plan.** Owns Phase 3: `skaal.binding`, the defaults table, `skaal.toml` env schema, the typed backend tokens, `TypePinViolation`, `BackendKindMismatch`.
3. **ADR 032 — Runtime/deploy rewire on `BoundPlan`.** Owns Phase 4.
4. **ADR 033 — Typing contract and `skaal stubs`.** Owns Phase 5.
5. **ADR 034 — `skaal plan` diff, `skaal map`, `skaal where`/`trace`, PR-comment action.** Owns Phase 6.
6. **ADR 035 — Docs, examples, migration guide.** Owns Phase 7 and the `v0.4.0` cut to `main`.

Each subsequent ADR follows the same template as this one: scope, decisions, implementation table, exit criteria, risks, non-goals, what comes next. Each one owns its own phase section in `notes/redesign-status.md`.

The redesign is done when the tracker reports every phase complete, `v0.4.0` is tagged on `main`, and ADR 028 §12's nine success criteria are all simultaneously true.
