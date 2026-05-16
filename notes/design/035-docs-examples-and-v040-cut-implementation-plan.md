# ADR 035 — Docs, examples, and the `v0.4.0` cut implementation plan

**Status:** Proposed
**Date:** 2026-05-16
**Related:** [ADR 028](028-code-first-infra-redesign.md) §11–§12; [ADR 029](029-redesign-foundation-implementation-plan.md); [ADR 030](030-inference-layer-implementation-plan.md); [ADR 031](031-binding-layer-implementation-plan.md); [ADR 032](032-runtime-deploy-on-bound-plan-implementation-plan.md); [ADR 033](033-typing-contract-and-stubs-implementation-plan.md); ADR 034 (Phase 6)
**Phase:** ADR 028 §9.7 (Phase 7)
**Target release tag:** `v0.4.0`

---

## Goal

Land the last phase of the [ADR 028](028-code-first-infra-redesign.md) redesign: rewrite the docs and examples for the code-first vocabulary, prove `examples/todo_api` and the BigQuery `.native()` walkthrough end-to-end against real cloud, and cut `v0.4.0` on `main`.

After Phase 7, every ADR 028 §12 success criterion is verifiable on a fresh checkout. The `v0.4.0-alpha` working branch squash-merges to `main` and the `v0.4.0` tag goes out to PyPI.

## Why this is its own ADR

Phases 0–6 rebuilt the framework. They left three deliverables for Phase 7 because each one only makes sense once the surface it documents is frozen:

1. **The docs site still describes the `0.3.x` constraint product.** Every page under `docs/` was written against the Z3 + catalog vocabulary deleted in Phase 1. Rewriting them earlier would have meant rewriting them twice — the inference / binding / runtime / deploy / stubs / plan surfaces all changed under the redesign. With Phases 2–6 closed, the docs can be rewritten against a stable target.
2. **Four examples still import Phase 1-deleted symbols.** `03_dash_app`, `04_mesh_counter`, `05_task_dashboard`, and the top-level `mesh_counter` all reference `VectorStore`, `Agent`, `EventLog`, `Saga`, `Durability`, `Scale`, `@handler`, or the mesh runtime. They're on disk but uncompilable. Phase 4 §4.11 deferred the deeper rewrite here.
3. **The end-to-end success criteria from ADR 028 §12 need their own proof commits.** "`examples/todo_api` deploys to AWS in under 5 minutes from a fresh checkout" and "`class Sales(Relational[BigQuery], table=True)` plus `await Sales.native()` resolves to `google.cloud.bigquery.Client`" are user-experience guarantees, not unit-testable contracts. They land as smoke tests + a recorded walkthrough.

Phase 7 is also where the release mechanics happen: branch promotion, squash-merge, tag, PyPI publish, GitHub release notes.

## Scope

In scope:

- Full docs rewrite under `docs/` against the code-first surface. Every page that mentions constraints, catalogs, `Latency` / `Durability` / `AccessPattern` / `Throughput`, `@app.handler` / `@app.scale` / `@app.shared`, the Z3 solver, or the `mesh/` Rust crate is either rewritten or deleted.
- `mkdocs.yml` rewrite — `site_description`, `footer_tagline`, nav, header_links, and footer_groups all reflect the code-first product. The "Architecture → Constraint Model" entry is removed; `docs/design/001-infrastructure-as-constraints.md` is moved to `docs/design/_archive/` and dropped from the nav.
- Examples sweep: `03_dash_app`, `04_mesh_counter`, `05_task_dashboard`, and `mesh_counter/` are rewritten on the code-first surface or deleted. The surviving example set is renumbered so the on-disk order matches the tutorials' progression.
- Two new working examples introduced explicitly for the ADR 028 §12 success criteria: `examples/bigquery_sales/` (the `Relational[BigQuery]` + `.native()` walkthrough), and a `tests/smoke/test_todo_api_aws.py` deploy-and-tear-down script gated on `SKAAL_RUN_AWS_SMOKE=1`.
- A "What's new in `v0.4.0`" page under `docs/whats-new.md` — a forward-looking summary of the code-first surface, not a backward-looking migration guide.
- `README.md` final pass: hero, status callout, three-line "Hello, world", install instructions for AWS extras, link to `docs/whats-new.md`.
- The `## Status` callout pointing at `notes/redesign-status.md` is replaced with a normal "Alpha → Stable" badge once `v0.4.0` ships.
- Cut `v0.4.0`: squash-merge `v0.4.0-alpha` → `main`, push the `v0.4.0` tag, verify the existing `release.yml` GitHub Action publishes to PyPI, draft the GitHub release notes.
- Tracker close-out: `notes/redesign-status.md` Phase 7 section ticks, Phase 0 / 1 maintainer-action checkboxes (`v0.4.0-alpha.0` through `v0.4.0-alpha.6` tags, archive tags) ticked or explicitly declined, and the tracker concludes with a one-line "Redesign complete — `v0.4.0` released on `<date>`" footer.

Out of scope (each lands later):

- **A `0.3.x` → `0.4.0` migration guide.** `0.3.x` was alpha software with no production users to migrate; the deletion was complete and the new surface is small enough to learn from `docs/getting-started.md` and the examples. Writing a migration guide would document a contract nobody depends on.
- **GCP-first parity with AWS in the deploy templates.** ADR 032 ships AWS first; the GCP template tree (`Pubsub`, `CloudRun`, `Firestore`, `Gcs`, `CloudSchedulerCloudRun`, `CloudTasksCloudRun`) is a 0.4.x point release. Phase 7 documents the AWS path; the GCP pages carry a "coming in 0.4.x" admonition.
- **An auto-publishing mkdocs preview per PR.** `docs.yml` already builds on push to `main`; preview-per-PR is a separate ops change.
- **A v0.5 roadmap document.** ADR 028 §10 already lists the deferred items; Phase 7 does not need a new planning doc.
- **A "production-readiness" checklist beyond the ADR 028 §12 nine criteria.** Those nine are the contract.

Out of scope permanently for Phase 7:

- Re-introducing any `0.3.x` symbol behind a deprecation shim. ADR 028's "no backwards-compatibility shims" stance holds through the release.
- Documenting the legacy `__skaal_storage__` / `__skaal_function__` / `__skaal_schedule__` / `__skaal_channel__` / `__skaal_job__` dunders. They were deleted in Phase 4 and the `tests/typing/test_legacy_dunders_gone.py` grep gate prevents reintroduction; docs never mentioned them publicly.

## Decision 1 — Docs are rewritten page-by-page, not regenerated

Every page under `docs/` is touched by hand. The redesign changed the user-facing vocabulary enough that a global find-and-replace would produce stilted prose; a page-by-page rewrite is faster than auditing search-and-replace output.

The rewrite landing order is fixed so the docs build stays green at every commit:

| Order | Page | Action |
|---|---|---|
| 1 | `docs/index.md` | Rewrite around `App` + typed primitives + `infer → bind → run/deploy`. Drop the Z3 / catalog framing. |
| 2 | `docs/getting-started.md` | Rewrite against `skaal init && skaal run`. Three-step "hello world": declare a `Store`, decorate a `@app.function`, `curl localhost:8000`. |
| 3 | `docs/how-it-works.md` | Rewrite around the four layers (primitives / inference / binding / deploy). Reference ADR 028 §6 for the architectural deep-dive. |
| 4 | `docs/tutorials/first-app.md` | Drop the constraint-driven counter framing; rewrite against `examples/01_hello_world` and `examples/counter`. |
| 5 | `docs/tutorials/http-api.md` | Verify against the current `examples/02_todo_api` + `App.mount(path, asgi_app)`. The Phase 4 mount-API reshape (ADR 032 §4.6) means every code snippet needs review. |
| 6 | `docs/tutorials/planning-and-deployment.md` | Rewrite around `skaal plan` (Phase 6 diff form), `skaal build`, `skaal deploy --env prod`, and `skaal.lock`. |
| 7 | `docs/tutorials/relational-and-migrations.md` | Rewrite against `class T(Relational[B], table=True)` (single backend generic per the §4.4 reshape). Include the BigQuery `.native()` example as the closing section. |
| 8 | `docs/tutorials/files-and-streaming.md` | Verify against `examples/06_fastapi_streaming` and `examples/07_file_upload_api`. |
| 9 | `docs/tutorials/index.md` | Reorder, retitle, drop dead links. |
| 10 | `docs/cli.md` + `docs/cli-configuration.md` | Rewrite against the Phase 1 CLI surface (`init`, `run`, `plan`, `map`, `where`, `trace`, `build`, `deploy`, `stubs`, `doctor`). The Phase 6 `plan` / `map` / `where` / `trace` verbs need their own subsections. |
| 11 | `docs/comparison.md` | Rewrite. The current comparison framing is "constraint solving vs. handwritten IaC"; the new framing is "code-first infra vs. IaC DSLs and platform CRDs". |
| 12 | `docs/faq.md` | Rewrite. Drop every Z3 / catalog / mesh question; add new entries for `.native()`, `@app.external`, type-pinning, and the `skaal stubs` cross-process flow. |
| 13 | `docs/platform-features.md` | Either rewrite around the typed-primitive + resilience-policy surface or fold into `how-it-works.md` and delete. The page exists to enumerate platform features; with `EventLog`, `Outbox`, `Saga`, `Projection`, `Agent`, and the vector backends gone, the surface to enumerate is small enough that a section in `how-it-works.md` is sufficient. |
| 14 | `docs/examples.md` | Rewrite against the post-sweep examples list (Decision 2). |
| 15 | `docs/catalogs.md` | **Delete.** Catalogs are gone. |
| 16 | `docs/http.md` | Verify against `App.mount(...)`. Likely a light edit. |
| 17 | `docs/whats-new.md` | **New page.** Forward-looking summary of the code-first surface: what `App`, `Store[T, B]`, `Relational[B]`, `@app.function`, `infer → bind`, `skaal stubs`, and the `.native()` escape buy you. Linked from `README.md` and `docs/index.md`. Not a migration guide. |
| 18 | `docs/reference/python-api*.md` | Regenerated from docstrings via the existing `mkdocstrings` plugin. The reference pages are derived; they update automatically once the source docstrings are clean. Touch only to fix nav and drop dead links to `patterns`, `agents`, `solver`, `catalog`. |
| 19 | `docs/design/001-infrastructure-as-constraints.md` | **Move** to `docs/design/_archive/001-infrastructure-as-constraints.md` and drop from the mkdocs nav. The page is historically interesting; deleting it is unnecessary, but it must not be discoverable as current docs. |
| 20 | `docs/design_system/` | Audit only — the design-system pages (icons, components, preview HTML) reference "constraint tokens" in filenames and copy. Rename the filenames to `code-first-tokens.*` and update internal references. The CSS / SVG primitives themselves are vocabulary-neutral; only the prose changes. |
| 21 | `mkdocs.yml` | Final pass — drop `catalogs.md` from nav, drop the "Architecture → Constraint Model" entry, drop the `Z3` external resource link, rewrite `site_description` and `footer_tagline`, drop the `Constraint Model` footer link. |

The rewrite is *not* a "checklist of fixes" — it's a fresh narrative. The expected diff per page is "delete the body, write a new one against the current ADRs," not "tweak phrasing." Treating it as a tweak is the failure mode; the prose was load-bearing for a different product.

## Decision 2 — The examples directory ends with one example per concept

The current examples tree mixes runnable code with constraint-era stragglers. The Phase 7 sweep is destructive:

| Path | Action |
|---|---|
| `examples/01_hello_world/` | Keep. Already runs against the code-first surface (verified in Phase 4 §4.11). |
| `examples/02_todo_api/` | Keep. End-to-end verified against `skaal run` in Phase 4. The AWS-deploy smoke test (Decision 4) targets this app. |
| `examples/03_dash_app/` | **Delete.** Dash is a single-file Plotly dashboard; the example duplicates `examples/06_fastapi_streaming` without adding a Skaal concept. If a Dash example is wanted in v0.5, file an issue. |
| `examples/04_mesh_counter/` | **Delete.** The mesh runtime was archived in Phase 1; nothing remains to demonstrate. |
| `examples/05_task_dashboard/` | **Delete.** Imports `VectorStore`, `Agent`, `EventLog`, `Saga`, `Durability`, `Persistent`, `Scale`, `ScaleStrategy`, `@handler` — every one of which was removed in Phase 1. A v0.5 rewrite ("complex composite app") is a separate piece of work; the redesign does not need it. |
| `examples/06_fastapi_streaming/` | Keep. Working as of Phase 4. |
| `examples/07_file_upload_api/` | Keep. Working as of Phase 4. |
| `examples/counter.py` | Keep. Smallest runnable surface. |
| `examples/fastapi_streaming.py` | Delete — the directory form (`06_fastapi_streaming/`) supersedes it. |
| `examples/file_upload_api.py` | Delete — the directory form (`07_file_upload_api/`) supersedes it. |
| `examples/mesh_counter/` | **Delete.** Mesh runtime gone. |
| `examples/session_cache.py` | Keep. The type-pinned `Store[T, Redis]` demonstration from Phase 4 §4.11. |
| `examples/team_directory.py` | Keep. |
| `examples/todo_api.py` | Keep alongside `examples/02_todo_api/` — both are exercised by Phase 4's runtime tests. |
| `examples/bigquery_sales/` | **New.** The `Relational[BigQuery]` + `.native()` walkthrough required by ADR 028 §12 success criterion 6. One module, one `Sales(Relational[BigQuery], table=True)` class, one `@app.function` that calls `await Sales.native()` and runs a BigQuery query. Documented in `docs/tutorials/relational-and-migrations.md`. |

After the sweep the examples directory holds, in order: `01_hello_world`, `02_todo_api`, `06_fastapi_streaming`, `07_file_upload_api`, `bigquery_sales`, plus the flat modules (`counter.py`, `session_cache.py`, `team_directory.py`, `todo_api.py`). Renumbering `06_fastapi_streaming` → `03_fastapi_streaming` and `07_file_upload_api` → `04_file_upload_api` is optional polish; the prefix is documentation-order, not API.

The deletions are recorded in `docs/whats-new.md` under "Examples removed in `v0.4.0`" so anyone arriving from a stale link sees what happened.

## Decision 3 — The BigQuery walkthrough is a real, runnable example

ADR 028 §12 criterion 6 requires:

```python
class Sales(Relational[BigQuery], table=True):
    ...

client = await Sales.native()      # google.cloud.bigquery.Client
```

…to (a) resolve in Pylance to `google.cloud.bigquery.Client`, (b) run against real BigQuery locally when `env.local.backends.bigquery` is configured, and (c) fail at config-load with `TypePinViolation` if a different backend is forced.

Phase 7 ships `examples/bigquery_sales/` as the live demonstration. The example:

- Declares one `Sales` table with a small schema (`sale_id`, `customer_id`, `amount_usd`, `closed_at`).
- Declares one `@app.function` (`recent_sales(days: int) -> list[dict]`) that runs a BigQuery query through the native client.
- Ships a `skaal.toml` snippet showing the `[env.local.backends.bigquery]` configuration (project ID, dataset, credentials via ADC).
- Ships an `examples/bigquery_sales/README.md` with two `curl` commands and a one-paragraph "what's happening" explanation.

The Phase 7 smoke test runs against a real BigQuery dataset gated on `SKAAL_RUN_BIGQUERY_SMOKE=1` and `GOOGLE_APPLICATION_CREDENTIALS`. CI does not run it by default; a maintainer runs it once before tagging `v0.4.0`.

Note on the type-pin shape: the success criterion in ADR 028 §12 was written before the Phase 4 §4.4 reshape that dropped the two-generic `Relational[T, B]` form in favour of single-generic `Relational[B]` with the class body as the row schema. The criterion's intent (BigQuery `.native()` resolves to the concrete client) is unchanged; the syntax in `docs/tutorials/relational-and-migrations.md` and `examples/bigquery_sales/` uses the current `Relational[BigQuery]` form. ADR 028 §12 will be amended in the same commit that introduces the BigQuery example to reflect the reshape.

The Phase 5b `.native()` per-token narrowing is also a precondition for criterion 6. If the strict-typing follow-up has not landed by the time Phase 7 starts, the example still runs (the runtime `.native()` from Phase 5a returns `Any`), but the criterion is recorded as "runtime green, type narrowing pending" until the per-token `NativeClient` declarations land. The release does not block on the type narrowing; the criterion is satisfied at runtime and the tracker carries the deferred typing as a known Phase 5b polish item.

## Decision 4 — The AWS smoke test is a maintainer-run script, not CI

ADR 028 §12 criterion 9 requires `examples/todo_api` to deploy to AWS in under 5 minutes from a fresh checkout. Running this in CI would mean (a) keeping live AWS credentials in GitHub Actions secrets, (b) tearing down resources on every PR, (c) accepting flaky failures from AWS rate-limits and IAM propagation. None of that is worth it for one success criterion.

The smoke test ships as `tests/smoke/test_todo_api_aws.py`, gated on `SKAAL_RUN_AWS_SMOKE=1`. The script:

1. `skaal init` into a tempdir.
2. Copies `examples/02_todo_api/app.py` and a minimal `skaal.toml` with `[env.prod.target] = "aws"` into the tempdir.
3. Runs `skaal deploy --env prod`, captures the start/finish wall-clock time, asserts under 300 seconds.
4. Hits the deployed API Gateway URL with a `POST /todos` + `GET /todos` smoke flow.
5. Runs `skaal destroy --env prod` (Phase 6 verb; if not yet implemented, falls back to `pulumi destroy` via the automation API).
6. Asserts the `skaal.lock` round-trip — re-running `skaal plan --env prod` after destroy reports the expected delete-rows.

A maintainer runs the script once before tagging `v0.4.0`. The result (timing, region, AWS account scrub) is recorded in `docs/whats-new.md`. Future regressions are caught by re-running the same script ad hoc; CI does not babysit it.

The fallback if the 5-minute budget is missed: profile, identify the slow step (most likely ECR push or Lambda cold-start retry), and either optimize or amend the criterion. The criterion exists to keep the deploy path honest; if 5 minutes is impossible on a cold AWS account but 7 minutes is consistent, the tracker reflects 7.

## Decision 5 — Cutting `v0.4.0` is a four-step ritual

The release is mechanical. The four steps run in order:

1. **Tracker close-out.** Every Phase 0–6 checkbox that gates `v0.4.0` is either ticked or explicitly declined with a one-line reason. The Phase 7 checklist below is fully ticked. The tracker's last paragraph reads "Redesign complete — `v0.4.0` released on `<date>`." This is the moment of no return for the alpha branch.
2. **Squash-merge `v0.4.0-alpha` → `main`.** One squash commit captures the entire redesign. The commit message is the rendered diff narrative — what was removed, what was added, link to ADR 028. This is the merge maintainers approve; nobody reviews the squash.
3. **Tag `v0.4.0` on `main`.** Existing `release.yml` GitHub Action triggers on `v*` tags and publishes to PyPI. The tag message is one paragraph + the link to `docs/whats-new.md`. Verify the action's `pypi-publish` job succeeds; if it fails, debug, fix, retag (`v0.4.0` → `v0.4.0.post1` if the artifact is broken; never delete a published tag).
4. **Publish GitHub release notes.** The notes are the same paragraph as the tag message plus a "What's new" link and a "Documentation" link. No changelog bullet list — the docs site is the changelog.

`CITATION.cff` is bumped to `0.4.0` as part of step 2. `pyproject.toml` version is bumped from `0.4.0a0` to `0.4.0` in the same commit. Both bumps are squashed into the merge commit so `main` never carries an intermediate alpha version.

Archive tags (`archive/v0.3.x-agent`, `archive/v0.3.x-patterns`, `archive/v0.3.x-vector`, `archive/v0.3.x-mesh`) are pushed by the maintainer between steps 1 and 2. The tags point at the pre-deletion commits on the alpha branch, which are reachable from `main`'s history through the squash commit's `parents` link.

## Implementation map

### 7.1 — Examples sweep

- Delete `examples/03_dash_app/`, `examples/04_mesh_counter/`, `examples/05_task_dashboard/`, `examples/mesh_counter/`, `examples/fastapi_streaming.py`, `examples/file_upload_api.py`.
- Create `examples/bigquery_sales/__init__.py`, `examples/bigquery_sales/app.py`, `examples/bigquery_sales/skaal.toml.example`, `examples/bigquery_sales/README.md`.
- Verify every remaining example imports cleanly under `pytest --collect-only`; add a `tests/examples/test_imports.py` collection test that imports each surviving example's `app` symbol.

### 7.2 — Docs rewrite

- Pages 1–17 from the Decision 1 table — written in landing order so each commit's mkdocs build is green.
- `docs/catalogs.md` deletion is a `git rm` plus a `mkdocs.yml` nav scrub plus a redirect entry in `docs/overrides/main.html` so existing `/catalogs/` URLs 301 to `/how-it-works/`.
- `docs/design/001-infrastructure-as-constraints.md` moves to `docs/design/_archive/`; `_archive/` is excluded from the mkdocs build via `exclude_docs:` in `mkdocs.yml`.
- `docs/whats-new.md` written last, after every other page has stabilised, so its "what's new" framing is accurate.

### 7.3 — `mkdocs.yml` rewrite

- `site_description: Code-first infrastructure for Python.`
- `footer_tagline:` rewritten to a one-sentence description of the code-first product. No "Z3", no "constraints", no "latency / durability / throughput".
- Nav: drop `catalogs.md`, drop "Architecture → Constraint Model", add "Get Started → What's New".
- `header_links`: drop the dead links.
- `footer_groups`: drop the "Constraint Model" and "Z3" entries; add a "What's New" link under "Docs".

### 7.4 — `README.md` final pass

- Status callout rewritten from "alpha, redesign in progress" to "alpha → stable, `v0.4.0` released".
- Three-line "Hello, world" snippet uses `App`, `Store[int]`, and a single `@app.function`. Verified runnable via the `tests/examples/test_imports.py` collection test.
- Install snippet adds `pip install "skaal[aws]"` and `pip install "skaal[gcp]"` lines.
- Link to `docs/whats-new.md`.

### 7.5 — Smoke tests

- `tests/smoke/test_todo_api_aws.py` — gated on `SKAAL_RUN_AWS_SMOKE=1`. Implements Decision 4.
- `tests/smoke/test_bigquery_sales.py` — gated on `SKAAL_RUN_BIGQUERY_SMOKE=1` and `GOOGLE_APPLICATION_CREDENTIALS`. Runs the `recent_sales` function against a real BigQuery dataset.
- Both smoke tests live under `tests/smoke/` (a new directory) so the default `pytest tests/` run picks them up but they skip without the env var set. CI's matrix does not opt in.

### 7.6 — Tracker close-out and release

- `notes/redesign-status.md` Phase 7 section gains the checklist below; ticks land as each item closes.
- `pyproject.toml` version bumped `0.4.0a0` → `0.4.0`; `CITATION.cff` version bumped `0.4.0-alpha` → `0.4.0`. Both bumps are part of the squash-merge commit, not separate commits.
- Squash-merge `v0.4.0-alpha` → `main`; tag `v0.4.0`; verify `release.yml` publishes; draft GitHub release notes.
- Final commit on `main` updates the tracker's last line to "Redesign complete — `v0.4.0` released on `<date>`."

## Phase 7 exit criteria

All nine ADR 028 §12 success criteria are simultaneously verifiable:

1. [ ] `skaal init && skaal run` requires zero arguments and zero config edits — verified by `tests/cli/test_init_run_end_to_end.py`.
2. [ ] `skaal plan --env prod` produces a deterministic diff readable in under 30 seconds — verified by Phase 6's `tests/cli/test_plan_diff.py` plus a timing assertion added in Phase 7.
3. [ ] `skaal deploy --env prod` writes `skaal.lock` and the next `skaal plan` is empty unless code changed — verified by the Decision 4 smoke test.
4. [ ] A `Store[T]` in one module is importable, typed, and usable from another module with no codegen step — verified by `tests/typing/test_reveal_types.py` (Phase 5) plus `examples/02_todo_api`.
5. [ ] `pyright --strict` green on `skaal/`, `examples/`, `tests/typing/`; every §6.13.3 `reveal_type` assertion passes — Phase 5b extended in Phase 7 to add `examples/` to the strict-typing surface in `pyrightconfig.json`.
6. [ ] `class Sales(Relational[BigQuery], table=True)` plus `await Sales.native()` resolves to `google.cloud.bigquery.Client` in Pylance, runs against real BigQuery locally per `env.local.backends.bigquery`, and a conflicting override fails with `TypePinViolation` at config-load — verified by `examples/bigquery_sales/` + the Decision 3 smoke test. ADR 028 §12's syntax updated to the single-generic shape.
7. [ ] Opening a PR posts an infra-diff comment automatically — verified end-to-end in Phase 6 by ADR 034.
8. [ ] The word "constraint" appears nowhere in user-facing docs, CLI help, or decorator signatures — verified by a `tests/docs/test_no_constraint_word.py` grep gate over `docs/` (excluding `docs/design/_archive/`), `skaal/cli/`'s help strings, and `skaal/__init__.py` `__all__` introspection on decorator signatures.
9. [ ] `examples/todo_api` walkthrough deploys to AWS in under 5 minutes from a fresh checkout — verified by the Decision 4 smoke test.

The Phase 7 internal checklist that gets ticked in `notes/redesign-status.md`:

- [ ] 7.1 Examples sweep complete (`03_dash_app`, `04_mesh_counter`, `05_task_dashboard`, `mesh_counter/`, `fastapi_streaming.py`, `file_upload_api.py` deleted; `bigquery_sales` added)
- [ ] 7.2 Docs rewrite complete (pages 1–18 landed; `catalogs.md` deleted; `001-infrastructure-as-constraints.md` archived)
- [ ] 7.3 `mkdocs.yml` rewritten
- [ ] 7.4 `README.md` final pass
- [ ] 7.5 Smoke tests landed under `tests/smoke/`
- [ ] 7.6 `pyright --strict` extended to `examples/`
- [ ] 7.7 `tests/docs/test_no_constraint_word.py` grep gate green
- [ ] 7.8 Decision 4 AWS smoke run by a maintainer; timing recorded in `docs/whats-new.md`
- [ ] 7.9 Decision 3 BigQuery smoke run by a maintainer; result recorded in `docs/whats-new.md`
- [ ] 7.10 Archive tags pushed
- [ ] 7.11 Alpha tags pushed (`v0.4.0-alpha.0` through `v0.4.0-alpha.6` ticked or explicitly declined)
- [ ] 7.12 `pyproject.toml` + `CITATION.cff` bumped to `0.4.0`
- [ ] 7.13 Squash-merge `v0.4.0-alpha` → `main`
- [ ] 7.14 `v0.4.0` tag pushed; `release.yml` publishes to PyPI; GitHub release notes drafted
- [ ] 7.15 Tracker footer updated to "Redesign complete — `v0.4.0` released on `<date>`"

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| The docs rewrite drags on past the alpha cadence because every page needs fresh prose. | The Decision 1 table is the work-breakdown structure. Pages land in order; each landing keeps the build green. Pages 1–9 (`index`, `getting-started`, `how-it-works`, the tutorials) are the load-bearing rewrite; pages 10–17 are smaller. If the rewrite stalls, ship pages 1–9 and gate `v0.4.0` on those; pages 10–17 can land as `v0.4.0.post1`. |
| The AWS smoke test takes longer than 5 minutes on a cold account and the criterion can't be met. | Decision 4's fallback: profile, identify the slow step, and either fix it or amend the criterion to the consistent observed time. The criterion exists to keep the deploy path honest, not to hit an arbitrary number. |
| The BigQuery `.native()` per-token typing (Phase 5b deferred polish) doesn't land before Phase 7 starts. | Decision 3's runtime walkthrough still works; the typing-narrowing piece is recorded as a known polish item. Criterion 6 is satisfied at runtime; the type narrowing ships in a 0.4.x point release. |
| Squash-merging `v0.4.0-alpha` → `main` loses commit-level history. | The alpha branch is preserved on `origin` (never force-deleted post-merge), and the archive tags pin the pre-Phase-1 deletions. Anyone wanting the per-commit history walks the branch. |
| `release.yml` fails to publish `v0.4.0` to PyPI on the first tag push. | Retag as `v0.4.0.post1` after fixing the workflow. Never delete and re-push the `v0.4.0` tag — PyPI rejects re-uploads under the same version. |
| A `0.3.x` user lands on `v0.4.0` and finds no migration guide. | The deletion was alpha-era; there are no production users to migrate. `docs/whats-new.md` explains what the new surface is and links to `docs/getting-started.md`. If a `0.3.x` user surfaces in an issue, point them at the alpha-branch tag and at the relevant tutorial. |

## Non-goals for this ADR

1. A `0.3.x` → `0.4.0` migration guide. The deletion was complete; the new surface is small enough to learn from `docs/getting-started.md`.
2. A `v0.4.0` changelog beyond `docs/whats-new.md` and the GitHub release notes. The docs site is the changelog.
3. GCP parity in deploy templates. A 0.4.x point release owns it.
4. A v0.5 roadmap. ADR 028 §10 already enumerates the deferred items.
5. CI-driven AWS/BigQuery smoke runs. Maintainer-run scripts gated on env vars are sufficient.
6. Backwards-compatibility shims for `0.3.x` symbols. ADR 028's "no shims" stance holds.

## What comes next

After `v0.4.0` ships:

1. **`v0.4.x` point releases** — GCP deploy templates, `.native()` per-token typing narrowing, any straggler bugs from the post-release feedback loop. Same `main` branch; no new alpha.
2. **v0.5 planning** — ADR 028 §10's deferred items (third-party `BackendProtocol`, multi-tenant deploys, vector backends as a v0.5 reintroduction, Pulumi state backend selection). New ADR series starting at 036.
3. **Tracker archival** — `notes/redesign-status.md` is moved to `notes/redesign-status-v0.4.0.md` as a historical record; a fresh tracker (or none) is set up for v0.5.
