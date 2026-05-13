# ADR 030 — Inference Layer Implementation Plan (Phase 2)

**Status:** Proposed
**Date:** 2026-05-13
**Related:** [ADR 028](028-code-first-infra-redesign.md) (the redesign), [ADR 029](029-redesign-foundation-implementation-plan.md) (Phases 0–1)
**Supersedes execution detail in:** ADR 028 §9 Phase 2

---

## Goal

Land Phase 2 of the [ADR 028](028-code-first-infra-redesign.md) redesign: a new package, `skaal.inference`, that walks an `App` and produces a deterministic, environment-independent `InferredPlan`.

`InferredPlan` is the contract every later phase consumes — binding (Phase 3) takes it as input; runtime/deploy (Phase 4) consume the `BoundPlan` derived from it; the typing-stub command (Phase 5) reads its `model_json_schema()`; plan-diff (Phase 6) compares two fingerprints. Phase 2's narrow job is to make that contract real, typed, and round-trippable.

## Scope

In scope:

- `skaal.inference` package with four modules — `model.py`, `walk.py`, `fingerprint.py`, `asgi.py`.
- A `__skaal_inferred__` metadata attribute populated by every surviving decorator (`@app.storage`, `@app.function`, `@app.schedule`, `@app.job`, `@app.channel`), carrying an `InferredResource`.
- `App.infer() -> InferredPlan` as the user-facing entry point.
- Test coverage for fingerprint determinism, pydantic round-tripping, and the recognised resource kinds.
- The pydantic models documented in ADR 028 §6.2 (`InferredPlan`, `InferredResource`, `SchemaRef`, `SourceLocation`, `ResourceOverrides`, `Edge`, `ResourceKind`).

Out of scope (each lands in its own ADR/phase):

- The binding layer, `BoundPlan`, defaults table, registry — Phase 3 / ADR 031.
- Replacing the legacy `__skaal_storage__` / `__skaal_function__` / `__skaal_schedule__` dunders. These still feed surviving code paths (`schedule.py`'s APScheduler wrapper, `relational.py` / `blob.py`'s `is_*_model` predicates) that Phase 4 rewires on top of `BoundPlan`. Phase 2 is **additive**: it adds `__skaal_inferred__` alongside the existing dunders; Phase 4 deletes the legacy ones once their consumers move.
- The full typed primitive surface (`Store[T, B]`, `Relational[T, B]`, `BlobStore[B]`, `Channel[T, B]` with `B` defaulted to `Backend`). The second generic parameter depends on the `Backend` token tree that Phase 3 ADR 031 builds; Phase 2 keeps the existing single-parameter generics (`Store[T]`, `Channel[T]`, `BlobStore`) and stubs in a non-functional `Backend` marker so Phase 3 can flesh it out without an `__init__.py` re-cut.
- The `App.mount(path: str, asgi_app: ASGIApplication)` signature reshape and the `FunctionRef[P, R]` typed return shape. Both are described in ADR 028 §6.4.1 / §6.4.2; both touch the user-facing decorator surface and are best landed alongside `@app.external` in the Phase 2/4 follow-up rather than mixed into the first inference cut. ADR 030's `asgi.py` recogniser reads the existing `mount_asgi` / `mount_wsgi` call-sites as a stand-in.
- `@app.external` decorator and `ExternalStorage` reshape — ADR 028 §6.4 calls for these in Phase 2, but they require the binding-layer concept of "user-supplied connection" to be coherent. Park until Phase 3.
- `pyright --strict skaal/` green. The codebase still carries pre-redesign typing debt under `skaal.relational`, `skaal.schedule`, and `skaal.backends`. Phase 5 (ADR 033) owns the strict-typing pass; Phase 2 makes its own contribution (`skaal.inference.*` is strict at construction) but does not block on the rest of the tree.

## Decision 1 — `InferredPlan` and friends are pydantic, frozen, `extra="forbid"`

Every model in `skaal.inference.model` is a `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`. Rationale (per ADR 028 §6.2):

1. **JSON-schema, validation, equality, and `model_dump_json()` come for free.** Every downstream consumer — the CLI, tests, the eventual editor plugin — operates on the same canonical shape.
2. **`frozen=True` is a contract.** An `InferredPlan` is the byte-stable input to fingerprinting (§6.7) and PR diffing (§6.9). Mutation after construction would invalidate the fingerprint silently; the frozen model makes that a runtime error.
3. **`extra="forbid"` is a contract.** A forward-compatible inference model would let unknown fields drift in; the redesign explicitly rejects that — every field is enumerated in ADR 028, and unknown fields are a typo.

The model surface in `skaal.inference.model` is exactly the seven types from ADR 028 §6.2: `SourceLocation`, `SchemaRef`, `ResourceOverrides`, `Edge`, `ResourceKind` (a `StrEnum`), `InferredResource`, `InferredPlan`.

`InferredResource.schema_` aliases to `schema` for JSON output (the field name `schema` collides with pydantic's `BaseModel.schema()` method on older pydantic versions); `model_dump_json(by_alias=True)` round-trips through `model_validate_json(...)` for every model.

## Decision 2 — Inference is additive at the decorator layer

Each surviving decorator continues to populate its existing `__skaal_*__` dunder; the *new* responsibility is to **also** populate `__skaal_inferred__: InferredResource` carrying the fields the inference layer needs.

```python
def storage(*, kind: StorageKind = "kv", indexes: list[SecondaryIndex] | None = None):
    def decorator(cls):
        # existing: cls.__skaal_storage__ = {...}
        # new:
        cls.__skaal_inferred__ = InferredResource(
            id=_resource_id(cls),
            kind={"kv": ResourceKind.STORE, "blob": ResourceKind.BLOB,
                  "relational": ResourceKind.RELATIONAL}[kind],
            source=SourceLocation.from_object(cls),
            schema_=SchemaRef.from_class(cls),
            indexes=tuple(indexes or ()),
        )
        return cls
    return decorator
```

The walker reads only `__skaal_inferred__`. Existing dunder consumers (`schedule.py:319`, `relational.py:43`, `blob.py:45`, `storage.py:338`, `module.py:_resolve_invokable`) are untouched. When Phase 4 rewires the runtime on `BoundPlan`, those consumers move to reading `__skaal_inferred__` and the legacy dunders are deleted in one pass.

Rationale for additive instead of replacing in this phase:

1. **Test surface stability.** 78 tests pass after Phase 1. Replacing dunders mid-phase risks turning a focused PR into a runtime-rewire-by-stealth.
2. **`__skaal_inferred__` is the new contract.** Inference consumers read only that; the legacy dunders are an implementation detail of soon-to-be-deleted code paths.
3. **The deletion is one PR, not seven.** Phase 4 owns the rewire — it is the place the legacy dunders die.

## Decision 3 — Fingerprinting is `model_dump_json(by_alias=True)` over a canonically-sorted tuple

`InferredPlan.fingerprint` is computed by:

1. Sorting `resources` by `(kind, id)` and `edges` by `(source_id, target_id, kind)`.
2. Emitting `model_dump_json(by_alias=True, exclude={"fingerprint"})` with `sort_keys=True` (pydantic 2 respects this through its serialiser).
3. Hashing the resulting bytes with SHA-256, truncated to the first 16 hex chars.

The fingerprint is recomputed by `walk.infer(app)` after the resource set is final; the caller does not pass one in. `InferredPlan.model_validate_json(payload)` re-checks the fingerprint against the deserialised resources and raises if it does not match — this protects against tampered or partial-write JSON.

Why SHA-256 truncated to 16 hex chars: short enough for a one-line PR comment, long enough that collisions are not a practical concern for the inference-graph cardinality the redesign targets.

## Decision 4 — Resource IDs are deterministic and module-qualified

`InferredResource.id` is the dotted path `<module>:<qualname>` for class-shaped resources and `<module>:<qualname>` for function-shaped resources (no leading slash, no env suffix). For functions inside a `Module`, the inference walk does **not** prefix the module name onto the id — the id is what `import` would name, not what `app.use(module)` namespaces. The runtime-level addressing (the namespaced form `<app>.<submodule>.<resource>`) is bound in Phase 3.

This is the same convention ADR 028 §6.5 uses in the `[env.<name>.overrides]` keys (`"acme.users:Users"`).

## Decision 5 — `asgi.py` recognises ASGI services from existing `mount_asgi` / `mount_wsgi` call-sites

ADR 028 §6.4.1 describes `app.mount(path, asgi_app)` as the canonical surface. The current `App` exposes `mount_asgi` and `mount_wsgi` from Phase 1. Rather than reshape the `App` API in Phase 2 (which would break every example simultaneously), the inference walker treats the presence of `_asgi_app` / `_asgi_attribute` on an `App` instance as an ASGI_SERVICE resource. The surfaces converge in Phase 4 when the runtime/deploy rewire happens.

If neither `_asgi_app` nor `_asgi_attribute` is set, no ASGI_SERVICE resource is emitted. WSGI apps emit ASGI_SERVICE too — Skaal wraps WSGI in `WSGIMiddleware` for serving; the inference distinction would only matter at deploy time, which is Phase 4.

## Implementation

### 2.1 — `skaal/inference/model.py`

The seven pydantic types from ADR 028 §6.2, plus a small set of constructors:

- `SourceLocation.from_object(obj)` — uses `inspect.getsourcefile` and `inspect.getsourcelines`; falls back to `("<unknown>", 0)` when source is unavailable (REPL, dynamically generated classes).
- `SchemaRef.from_class(cls)` — looks up the class's pydantic / SQLModel `model_json_schema()` (or returns `None` for non-schema-bearing classes); fingerprints with `hashlib.sha256(canonical_json).hexdigest()[:16]`.
- `InferredResource.id_for(obj)` — the `<module>:<qualname>` form used by every decorator.

`SecondaryIndex` is imported from `skaal.types.storage`; the existing type already meets the frozen-pydantic shape.

### 2.2 — `skaal/inference/walk.py`

Single public function:

```python
def infer(app: App) -> InferredPlan: ...
```

It walks `app._collect_all()`, plus `app._collect_jobs()`, plus the ASGI recogniser in `asgi.py`. For each registered object:

| Source bucket | Predicate | Emitted `ResourceKind` |
|---|---|---|
| `module._storage` | `getattr(cls, "__skaal_inferred__", None)` is `STORE`/`RELATIONAL`/`BLOB` | match |
| `module._functions` | `__skaal_inferred__` kind `FUNCTION` | `FUNCTION` |
| `module._jobs` | `__skaal_inferred__` kind `JOB` | `JOB` |
| `module._channels` | `__skaal_inferred__` kind `CHANNEL` | `CHANNEL` |
| `module._schedules` | `__skaal_inferred__` kind `SCHEDULE` | `SCHEDULE` |
| `app._asgi_app` or `app._wsgi_app` set | `asgi.recognise_mount(app)` returns `True` | `ASGI_SERVICE` |
| `module._secrets` | `SecretRef` instances | `SECRET` |

Edges are not produced in this phase. The inference walker leaves `InferredPlan.edges = ()`; emitting reads/writes/publishes/subscribes/invokes edges requires the bytecode-level call-graph walker described in ADR 028 §6.11 (traceability), which is Phase 6's responsibility. Phase 2's contract is "every resource is enumerated"; edges are additive and do not change resource enumeration.

### 2.3 — `skaal/inference/fingerprint.py`

```python
def fingerprint_plan(plan: InferredPlan) -> str: ...
def fingerprint_resource(res: InferredResource) -> str: ...
```

Both follow Decision 3. `fingerprint_plan` is called by `walk.infer` after the resources/edges are assembled; the result is set on `InferredPlan.fingerprint` before the model is frozen (via `model_construct` to bypass the frozen constraint during initial construction, then re-validated).

### 2.4 — `skaal/inference/asgi.py`

```python
def recognise_mount(app: App) -> InferredResource | None: ...
```

Returns an `ASGI_SERVICE` `InferredResource` when `app._asgi_app is not None` or `app._wsgi_app is not None`; the source location is the call-site of `mount_asgi` / `mount_wsgi` (best-effort via `inspect.stack()` at decoration time, recorded on the `App` instance when `mount_*` is called). When the source location cannot be determined, falls back to the `App` instance's `__class__` location.

### 2.5 — Decorator updates

Each of these gets one new line that constructs an `InferredResource` and assigns it to `target.__skaal_inferred__`:

- `skaal/decorators.py::storage`
- `skaal/decorators.py::function`
- `skaal/module.py::Module.storage` (delegates to the decorator above; no change needed)
- `skaal/module.py::Module.function` (same)
- `skaal/module.py::Module.job`
- `skaal/module.py::Module.channel`
- `skaal/module.py::Module.schedule`

The existing dunder assignments remain. The new attribute is the *additional* output, not a replacement.

### 2.6 — `App.infer()`

A two-line method on `App`:

```python
class App(Module):
    def infer(self) -> InferredPlan:
        from skaal.inference.walk import infer as _infer
        return _infer(self)
```

It is also exposed as `skaal.inference.infer(app)` for callers that prefer the function form (CLI, future GitHub Action).

### 2.7 — Public API exports

`skaal/__init__.py` `__all__` grows by the inference-model names:

```python
# new
from skaal.inference import (
    Edge,
    InferredPlan,
    InferredResource,
    ResourceKind,
    ResourceOverrides,
    SchemaRef,
    SourceLocation,
    infer,
)
```

All seven type names plus the `infer` callable join `__all__`. The order follows the existing alphabetical convention.

### 2.8 — Tests

New under `tests/inference/`:

- `test_model.py` — every pydantic type round-trips through `model_dump_json(by_alias=True)` → `model_validate_json`. `extra="forbid"` rejects unknown fields. `ResourceKind` enum has the nine variants from ADR 028 §6.2.
- `test_fingerprint.py` — same `InferredPlan` constructed in two different resource orders has the same fingerprint. Adding/removing a single resource changes the fingerprint deterministically. The fingerprint is 16 hex chars.
- `test_walk.py` — a minimal `App` with one `Store`, one `BlobStore`, one `Relational`, one `@function`, one `@schedule`, and one `@job` produces a plan with six resources of the correct kinds; the source locations point at the test module; the resource IDs follow the `<module>:<qualname>` convention.
- `test_asgi.py` — calling `App.mount_asgi(fastapi_app, attribute="...")` and `App.mount_wsgi(wsgi_app, attribute="...")` both produce an `ASGI_SERVICE` resource; not calling either produces none.

## Exit criteria

1. `App.infer()` returns an `InferredPlan` for a minimal app containing each resource shape; the plan validates against `InferredPlan.model_json_schema()`.
2. `make lint && make typecheck && make test` are green. The `skaal/inference/` package is included in the mypy default scope (not relaxed).
3. `notes/redesign-status.md` Phase 2 section is filled in and ticks the four checkpoints (model, walk, fingerprint, asgi) plus the new-tests checkpoint.
4. Release tag `v0.4.0-alpha.2` is **not** pushed by this PR — that is a maintainer action, tracked in the status file alongside the Phase 1 `v0.4.0-alpha.1` tag.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| `inspect.getsourcefile` fails for dynamically-created classes (REPL, factory functions). | `SourceLocation.from_object` falls back to `("<unknown>", 0)`. Inference does not raise on missing source. |
| The fingerprint is unstable across pydantic versions (e.g. `model_dump_json` key order). | The fingerprint sorts resources and edges explicitly, and `model_dump_json(by_alias=True)` is invoked with `sort_keys` enforced at the JSON layer (`json.dumps(... , sort_keys=True)` on the pydantic-emitted dict). The fingerprint test asserts byte-stability across two equivalent constructions. |
| Existing decorator consumers break because `__skaal_inferred__` shadows something. | The attribute name is namespaced under `__skaal_*`; it does not conflict with any pydantic, SQLModel, or stdlib attribute. The test suite is the canary. |
| The walker double-counts a resource that lives in both `module._storage` and `module._channels`. | The walker uses `id(obj)` deduplication: every `InferredResource` is emitted at most once per `id(obj)`, regardless of how many module buckets it appears in. |
| Phase 4's later replacement of legacy dunders breaks tests that read both. | Phase 4's tests will assert the legacy dunders are gone after that phase exits. Phase 2 explicitly keeps both alive. |

## Non-goals

1. Edges (`InferredPlan.edges` is always `()` after Phase 2). Phase 6 owns the call-graph walker.
2. Reshape of `App.mount` to `(path, asgi_app)`. Phase 4 owns this.
3. `Store[T, Backend]` second-parameter typing. Phase 3 owns the `Backend` token tree.
4. `FunctionRef[P, R]` typed return shape. Phase 4 owns the runtime that consumes it.
5. `@app.external` decorator. Phase 3 owns it (it depends on the binding-layer concept of user-supplied connections).
6. CLI integration of `skaal plan` against `InferredPlan`. The CLI verb still prints "not yet implemented in 0.4.0-alpha" until Phase 3 has a `BoundPlan` to diff against.

## What comes next

1. **ADR 031 — Binding layer and backend registry implementation plan.** Owns Phase 3 of ADR 028 §9: `skaal.binding`, the defaults table, `Environment`, `LockFile`, the typed `Backend` tokens, `TypePinViolation`, `BackendKindMismatch`, and the second generic parameter on the typed primitives.
2. After ADR 031: `pyright --strict` for `skaal.inference.*` and `skaal.binding.*` is added to the CI matrix as a separate gate from the wider mypy run.
