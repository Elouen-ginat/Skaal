# ADR 033 — Typing contract and cross-process stubs implementation plan

**Status:** Proposed
**Date:** 2026-05-16
**Related:** [ADR 028](028-code-first-infra-redesign.md) §6.6, §6.13, §9.5; [ADR 029](029-redesign-foundation-implementation-plan.md); [ADR 030](030-inference-layer-implementation-plan.md); [ADR 031](031-binding-layer-implementation-plan.md); [ADR 032](032-runtime-deploy-on-bound-plan-implementation-plan.md)
**Phase:** ADR 028 §9.5 (Phase 5)
**Target alpha tag:** `v0.4.0-alpha.5`

---

## Goal

Make the framework's typing contract (ADR 028 §6.13) load-bearing and ship the one cross-process tool that genuinely needs codegen (`skaal stubs`, ADR 028 §6.6.1).

Concretely, this ADR is what lets a reader of `examples/todo_api` open VSCode, hover over `Todos.put`, and see the typed signature — with no build step in between — and what lets a *different* project import a typed `.pyi` package describing those same primitives so cross-service callers get LSP completion for `Todos` and every `@app.function`.

## Why this is its own ADR

Phases 2–4 added new public surface; Phase 5 declares which parts of that surface the IDE and type checker treat as load-bearing. The previous phases focused on *runtime correctness* — `infer` returns the right plan, `bind` picks the right backend, `LocalRuntime.serve` wires the right adapters. Phase 5 focuses on the *static contract*: which symbols a downstream consumer can hover, autocomplete, and `Go to Definition` through.

Three operational questions Phase 4 deliberately did not answer:

1. **What does `pyright --strict` consider green?** A naive `pyright --strict skaal/` run today reports 37+ errors, the vast majority of them missing optional-extras imports (`pulumi_aws`, `boto3`, `aioboto3`, `uvicorn`, `watchfiles`). Without a checked-in `pyrightconfig.json` declaring what counts as the *core* type surface, every contributor's "is my type pass green?" answer is different.
2. **How are the §6.13.3 properties tested?** The table lists ten discoverability properties. None of them have tests today. Phase 5 names how each row is verified (subprocess `pyright` runs, `__all__` introspection, ruff/grep gates, `reveal_type` files).
3. **What is the `skaal stubs` contract?** ADR 028 §6.6.1 sketches the verb but does not pin the on-disk shape, the validation surface, or the consuming project's setup. Phase 5 ships that contract end-to-end.

## Scope

In scope:

- `pyrightconfig.json` at the repo root, pinning the strict-typing surface to the package's pure-Python core and excluding optional-extras-dependent submodules until they are individually cleaned.
- `tests/typing/` package — three new test modules: `test_no_string_backend.py`, `test_no_any_leaks.py`, `test_reveal_types.py`.
- Restoring the `@function` decorator's `ParamSpec` / `TypeVar` signature preservation so `reveal_type(signup)` resolves to `FunctionRef[[User], User]`.
- The typed `.native()` escape on `Store[T, B]` / `Relational[B]` / `BlobStore[B]` / `Channel[T, B]`, returning the bound backend's native client.
- `skaal/stubs/` package — `manifest.py`, `emit.py`, and the `skaal stubs` CLI verb.
- A `make pyright` target wired into the `dev` group; CI runs it as an *advisory* job during Phase 5a, blocking in Phase 5b.
- ADR 028 §6.13.3 row-by-row test coverage.

Out of scope (Phase 5b — landed in a follow-up commit on the same branch):

- Driving `pyright --strict skaal/ examples/ tests/typing/` to zero errors. This requires either installing every optional extra in the type-check job or annotating each optional import with a TYPE_CHECKING fallback; the surface is wide enough to deserve its own commit.
- Restoring the coverage floor from 40 → 60. The floor moves once Phase 5a's new tests have landed and the post-Phase-4 baseline (currently 57.1% with the test extras installed) is exceeded with margin.
- A Pyright LSP plugin for VSCode. The user-facing instructions are a `pyrightconfig.json` snippet in `docs/typing.md`; no plugin code ships.

Out of scope permanently:

- A `mypy --strict` run alongside `pyright --strict`. The framework already runs `mypy` in default mode for CI; `pyright` is the strict gate. Doubling up bloats the matrix without catching more.
- A typed-stubs generator for *every* installed Skaal app on a developer's machine. `skaal stubs` is the cross-process bridge only — single-process callers import the primitive classes directly per ADR 028 §6.6.

## Decision 1 — `pyrightconfig.json` declares the strict-typing surface

A new `pyrightconfig.json` at the repo root names exactly which paths `pyright --strict` is expected to land on green. The motivation is the same as `[tool.mypy].exclude` for `mypy`: the strict gate needs a stable scope that does not include code paths still being rewritten.

```jsonc
{
  "include": ["skaal", "tests/typing"],
  "exclude": [
    "skaal/deploy/templates",
    "skaal/cli/templates",
    "**/__pycache__"
  ],
  "ignore": [
    "skaal/deploy/aws",     // Phase 5b: optional pulumi_aws import
    "skaal/secrets/aws.py", // Phase 5b: optional aioboto3 import
    "skaal/secrets/gcp.py", // Phase 5b: optional google-cloud-secret-manager
    "skaal/runtime/local.py", // Phase 5b: optional uvicorn import
    "skaal/types/cli.py",     // Phase 5b: optional watchfiles import
    "skaal/backends/dynamodb_backend.py",  // Phase 5b: optional boto3 import
    "skaal/backends/postgres_backend.py",  // Phase 5b: optional asyncpg import
    "skaal/backends/firestore_backend.py", // Phase 5b: optional google-cloud-firestore
    "skaal/backends/s3_blob_backend.py",   // Phase 5b: optional s3fs
    "skaal/backends/gcs_blob_backend.py"   // Phase 5b: optional gcsfs
  ],
  "strict": ["skaal"],
  "pythonVersion": "3.11",
  "reportMissingTypeStubs": false,
  "reportPrivateUsage": false,
  "useLibraryCodeForTypes": true
}
```

The `ignore` list shrinks to zero as each cleanup PR lands; the final entry deleted closes Phase 5b.

`reportMissingTypeStubs: false` and `useLibraryCodeForTypes: true` are necessary because the upstream `redis`, `sqlmodel`, `apscheduler`, `pulumi`, and `boto3` packages ship `.pyi` files that pyright resolves in `useLibraryCodeForTypes` mode. Setting these is what made the rest of the redesign keep moving — Pylance for the example apps was already implicitly running with these defaults.

## Decision 2 — The three `tests/typing/` modules

Each one targets a specific subset of §6.13.3:

| Module | §6.13.3 rows covered | Mechanism |
|---|---|---|
| `test_no_string_backend.py` | "No string-typed backend at declaration sites" | `Path.rglob("*.py")` over `skaal/` and `examples/`, `re.search(r"\bbackend\s*=\s*[\"']")` rejected outside `skaal/binding/` and `skaal/inference/` (where the *runtime* `backend="…"` field on `ResourceOverrides` lives). |
| `test_no_any_leaks.py` | "No `Any` leaks from public API" | Walk `skaal.__all__`, resolve each symbol via `typing.get_type_hints`, fail if any public function's return type or any public class's public method's return type is `Any` *and* the symbol is annotated. The test is intentionally narrow (it does not chase nested generics) — its job is to catch a `def function(...) -> Any` regression on a top-level export, not to be a substitute for `pyright`. |
| `test_reveal_types.py` | All other §6.13.3 rows | A pytest module that writes a small temp `.py` file invoking `reveal_type(...)` on representative primitives, runs `pyright --outputjson` against it, and asserts the revealed types against expected strings. Skipped when `pyright` is not on `PATH` so the suite stays green for contributors who only have `mypy` installed; CI installs `pyright` via the `typecheck` group, so the assertion runs there. |

`test_reveal_types.py` is the row-by-row implementation of the §6.13.3 table. Each row's expected `reveal_type` string is parametrised so a future ADR that extends §6.13.3 only needs to add a parameter, not a new test function.

## Decision 3 — `@function` returns `FunctionRef[P, R]`, not `FunctionRef[..., Any]`

The Phase 4 decorator landed with `Callable[[Callable[..., Any]], FunctionRef[..., Any]]` as the return type because the typed return shape was scheduled for Phase 5. The Phase 5 form preserves the wrapped callable's `ParamSpec` and return type via a `Callable[[Callable[P, R]], FunctionRef[P, R]]` decorator factory.

The decorator continues to be parens-required (`@app.function()`) — the existing call sites in `examples/` already use this form, so no migration. The factory's outer signature is unchanged; only the inner type narrows. Pyright then infers:

- `class FunctionRef(Generic[P, R])`
- `FunctionRef.__call__(self, *args: P.args, **kwargs: P.kwargs) -> R | Awaitable[R]`
- The variants for async functions (where the wrapped body returns `Awaitable[R]`) and sync functions (where the body returns `R` directly) are covered by overloads on the decorator.

This is the §6.13.3 "Decorator preserves signatures" row.

## Decision 4 — `.native()` exists on every primitive, returning `Any` in Phase 5a

ADR 028 §6.13.4 §1 commits to "`.native()` only exists on type-pinned primitives." Implementing that contract — where `Pylance` reports `Cannot access member "native"` on `Store[User]` but accepts `await Cache.native()` on `Store[Session, Redis]` — requires per-token overload pairs whose number scales with the registered backends.

Phase 5a ships the *runtime* of `.native()` on all four primitives, returning the wired backend's native client (`cls._backend.native` when defined, else `cls._backend` itself). The static-type narrowing — making `await Cache.native()` resolve to `redis.asyncio.Redis` — is a Phase 5b deliverable that depends on the `pyright --strict` sweep landing the `NativeClient: type[NativeClientT]` declaration on every concrete `Backend` token.

The Phase 5a `.native()` return type is `Any` and the rendered `reveal_type` is `Any`. The §6.13.3 row "Un-pinned class has no `.native()`" is therefore deferred to Phase 5b. The remaining rows that don't depend on `.native()` typing (decorator signatures, mount typing, pydantic round-trip, no-string-backend) land in Phase 5a.

## Decision 5 — `skaal/stubs/` ships a one-shot `.pyi` emitter

The contract (ADR 028 §6.6.1):

```bash
$ skaal stubs --from ./services/billing --to ./apps/web/_stubs --as billing_stubs
```

The output is a single Python package with three files plus one per resource:

```txt
billing_stubs/
├── __init__.pyi            # re-exports
├── py.typed                # PEP 561 marker (empty file)
├── _manifest.json          # validated StubManifest, source app metadata
├── stores.pyi              # `class Customers(Store[Customer, Backend]): ...`
├── functions.pyi           # `def signup(user: User) -> User: ...`
└── relational.pyi          # `class Sales(Relational): ...`
```

`_manifest.json` carries the version of the source app, the inferred-plan fingerprint, the Skaal version, and the timestamp. The consuming project pins the manifest in its own VCS so a stale stub package is detectable.

Stub bodies are *names plus typed signatures*. They have no implementation. The IDE chases imports to the `.pyi` and stops. The PEP 561 `py.typed` marker tells `pyright` the package is a `partial-stub`.

Validation:

- The source app must be importable. `skaal stubs --from <path>` adds `<path>` to `sys.path`, imports the package whose `App` is discovered by walking `App.__subclasses__()`, and rejects ambiguous (multiple-`App`) trees with a clear error.
- The target directory must be empty *or* an existing stub package whose `_manifest.json` reports the same `--as <pkg>` name. Re-running with the same arguments is idempotent; a mismatched name is an error.
- Every emitted symbol is re-exported from `__init__.pyi` so consumers write `from billing_stubs import Customers` instead of `from billing_stubs.stores import Customers`.

Out of scope (deferred to v0.5):

- Type-checking the emitted `.pyi` against the source app's `BoundPlan`. Pyright on the consuming side already catches mismatches at use sites; a server-side conformance check would be a separate ADR.
- `skaal stubs --watch` for continuous regeneration. The CLI is one-shot; CI in the consuming project regenerates on PR.

## Implementation map

### 5.1 — `skaal/stubs/` package

- `skaal/stubs/__init__.py` exports `StubManifest`, `emit_stubs`, `discover_app`.
- `skaal/stubs/manifest.py` — pydantic `StubManifest` model, frozen, `extra="forbid"`. Fields: `package_name: str`, `source_module: str`, `source_app: str`, `app_fingerprint: str | None`, `skaal_version: str`, `generated_at: datetime`, `resources: tuple[StubResourceRef, ...]`. Each `StubResourceRef` carries `id`, `kind`, `module`, `qualname`.
- `skaal/stubs/emit.py` — `emit_stubs(*, app, out_dir, package_name) -> Path`. Walks `app.infer()`, groups resources by kind, emits one `.pyi` file per kind plus the index. Uses `inspect.getsource` and `inspect.signature` for callables; for `Store` / `Relational` / `BlobStore` / `Channel` subclasses it reads `__skaal_value_type__` (or the typed parameter on the parametrised base) and emits the typed generic shape.
- The emitter never imports `jinja2` — `.pyi` files are short and structured enough to compose with f-strings and `ast.unparse`.

### 5.2 — `skaal stubs` CLI verb

- `skaal/cli/stubs_cmd.py` — typer app, args mirror ADR 028 §6.6.1: `--from <path>`, `--to <out>`, `--as <pkg>`. Resolves the source `App` instance, dispatches to `emit_stubs`, prints a one-line summary on success.
- `skaal/cli/main.py` adds `app.add_typer(stubs_app, name="stubs")` after the existing `doctor` registration.

### 5.3 — `tests/stubs/`

- `tests/stubs/test_manifest.py` — round-trip the pydantic model, validate the forbid-extras rule.
- `tests/stubs/test_emit.py` — emit against the in-process `examples.counter` app, assert the directory layout and `__init__.pyi` contents.
- `tests/stubs/test_cli.py` — invoke the typer app with `runner.invoke`, point `--from` at a small temp module, assert the resulting `.pyi` parses with `ast.parse` and contains the expected resource names.

### 5.4 — `tests/typing/`

- `tests/typing/test_no_string_backend.py` — the grep gate from Decision 2.
- `tests/typing/test_no_any_leaks.py` — the public-API introspection from Decision 2.
- `tests/typing/test_reveal_types.py` — parametrised pyright-subprocess assertions for the §6.13.3 rows that don't depend on `.native()` typing in Phase 5a.

### 5.5 — Decorator typing

- `skaal/decorators.py` — `@function` returns `Callable[[Callable[P, Awaitable[R]] | Callable[P, R]], FunctionRef[P, R]]`. `FunctionRef.__call__` is typed via the same `ParamSpec`/`TypeVar` pair; the inner body keeps the `Awaitable[Any]` runtime fallback because the wrapped callable's return is still resolved at call time.

### 5.6 — `.native()` runtime

- `skaal/storage.py`, `skaal/blob.py`, `skaal/channel.py`, `skaal/relational.py` — each gains an `async def native(self_or_cls) -> Any` method that returns the wired backend's `.native` attribute when defined, else the backend instance itself. No-backend (un-wired) raises the existing `NotImplementedError` shape.

### 5.7 — `pyrightconfig.json`

- New file at repo root with the contents in Decision 1.

### 5.8 — Tooling

- `pyproject.toml` `[dependency-groups].typecheck` gains `pyright>=1.1.408`.
- `Makefile` `pyright` target: `uv run pyright`. The existing `make typecheck` keeps running `mypy`; `make pyright` is the strict-side complement. Phase 5b folds `pyright` into `make ci`.
- `.github/workflows/ci.yml` — a new `pyright` job (matrix Python 3.11) running `uv run pyright skaal/ tests/typing/`. **Continues on error** during Phase 5a so the gate is visible without blocking unrelated PRs; the `continue-on-error: true` flag is removed when Phase 5b closes.

### 5.9 — Tracker

- `notes/redesign-status.md` gains the Phase 5 checklist with the items above; the coverage-floor restoration sits at the bottom as a deferred Phase 5b item.

## Phase 5 exit criteria

1. `make test` is green; `tests/typing/` is in the suite.
2. `make pyright` passes against the surface declared in `pyrightconfig.json` (every path *not* in `ignore` is strict-clean).
3. `skaal stubs --from examples/counter --to /tmp/cstubs --as counter_stubs` produces a stub package whose `.pyi` files parse, whose `_manifest.json` round-trips through `StubManifest.model_validate_json`, and whose `from counter_stubs import Counts` resolves in a fresh `pyright` run on the consuming project.
4. The §6.13.3 rows tested in Phase 5a (everything except `.native()` typing) pass.
5. CI's `pyright` job is registered and reports its status on every PR.
6. The tracker reflects Phase 5a as complete with Phase 5b's punch list (strict-clean sweep + coverage-floor restore + `.native()` typing) enumerated.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| `pyright`'s strict mode catches a latent bug in a runtime path nobody noticed (e.g., a missing `await`). | This is the gate's job. Fix the bug. |
| `pyright` versions differ between contributors' editors and CI, producing "green locally, red in CI" surprises. | The `typecheck` group pins `pyright>=1.1.408`; CI installs the same version. Editors that ship Pylance pick up the same engine but a different version cadence — `pyrightconfig.json` minimises the diff. |
| `skaal stubs` emits stale stubs after `app.infer()` changes shape. | The `_manifest.json` carries the source-app's inferred-plan fingerprint. Consuming projects can grep for a mismatched fingerprint at PR time (a follow-up CI integration). The CLI is one-shot — staleness is intentional, not silent. |
| The `tests/typing/test_reveal_types.py` subprocess approach is slow. | The subprocess runs once per pytest session against a single temp file; the file holds every `reveal_type(...)` call. The marginal cost per row is one `pyright` parse of one extra line — under 0.5s total. |
| Phase 5b takes longer than expected and the coverage floor stays at 40. | The floor is a tracker checkbox, not a release blocker. Phase 7 also re-asserts the floor as part of `v0.4.0`. The risk is "alpha looks less polished," not "broken product." |

## Non-goals for this ADR

1. Building a Pyright plugin or VSCode extension. The IDE story is "install Pylance, point `pyrightconfig.json` at the project, done."
2. Server-side conformance checking of emitted `.pyi` against the source app. The consuming project's `pyright` run is the conformance check.
3. Multi-language stubs (TypeScript, Go). v1 emits Python stubs only.
4. Re-exposing `mypy` strict mode. Pyright is the strict gate.
5. A migration guide for `0.3.x` users — Phase 7 (ADR 035) owns that.

## What comes next

After Phase 5a lands on `claude/redesign-phase-5-jBYV6`:

1. **Phase 5b** — strict-clean sweep on the `ignore`-listed modules, full `.native()` typing on the primitives, `pyright` CI job's `continue-on-error: true` removal, coverage-floor restoration. Same branch; not a new ADR.
2. **ADR 034 — `skaal plan` diff, `map`, `where`, `trace`, PR-comment Action.** Phase 6.
3. **ADR 035 — Docs, examples, migration guide.** Phase 7 and the `v0.4.0` cut.
