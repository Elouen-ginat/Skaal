# ADR 036 — Public API naming critique and proposed refresh

**Status:** Proposed (discussion draft — not yet accepted)
**Date:** 2026-05-17
**Related:** [ADR 028](028-code-first-infra-redesign.md) §6 (the surface this critiques); [ADR 029](029-redesign-foundation-implementation-plan.md) (the phase plan that froze the names); [ADR 035](035-docs-examples-and-v040-cut-implementation-plan.md) (Phase 7, the last viable window to land breaking renames before `v0.4.0`)
**Phase:** Pre-`v0.4.0` (sequenced ahead of [ADR 035](035-docs-examples-and-v040-cut-implementation-plan.md) Phase 7 if accepted; otherwise deferred to `v0.5.x`)

---

## Why this ADR exists

The ADR 028 redesign committed to *no backwards-compatibility shims* for the `0.3.x` constraint vocabulary. That window — where breaking renames cost zero compatibility debt — is still open until `v0.4.0` cuts. Once we ship `v0.4.0`, every name in `skaal/__init__.py`'s `__all__` becomes load-bearing, and a second rename cycle would itself require a deprecation phase.

This ADR critiques the names currently exported by `skaal/__init__.py` (and the verbs in `skaal.api`), and proposes a coherent rename pass. It is intentionally written **before** the Phase 7 docs rewrite: rewriting the docs against names we then decide to change is the most expensive way to discover a naming problem.

The critique is opinionated by design. Each rename either survives an explicit rationale or is dropped. Names already considered and *kept* are listed under [§"Deliberately kept"](#deliberately-kept).

## Critique — what's wrong with the current names

### 1. The resource-primitive family is inconsistent

Today: `Store[T, B]`, `BlobStore[B]`, `Channel[T, B]`, `Relational[T]`.

- Two names end in the suffix `Store` (`Store`, `BlobStore`); two don't (`Channel`, `Relational`). A user scanning the public API can't predict the next primitive's shape.
- `Relational` is an adjective being used as a noun. The thing is a *table*; "relational" describes the database family, not the resource. Most users will type `Table` and miss the symbol.
- `Channel` overloads — Go channels, Slack channels, generic comms. The pub/sub-industry term is `Topic`; the work-queue-industry term is `Queue`. `Channel` was picked precisely because it doesn't commit to either, but the cost of that abstraction is that users can't tell what semantics they're getting.
- `BlobStore[B]` reads as "binary-large-object store"; the contained item is a `BlobObject` — a tautological "binary-large-object object".

### 2. The decorator vocabulary mixes parts of speech

Today: `@app.storage`, `@app.function`, `@app.external`, `@app.schedule`, `@app.job`.

- `@app.storage` is a noun (the kind of thing).
- `@app.function` is also a noun, but the thing being decorated is *already* a function — the decorator's job is to mark this particular function as **exposed** / **invokable** / **a handler**. Naming the decorator after the type of the thing it wraps reads as a declaration, but the act is registration.
- `@app.external` is an adjective ("external to what?"). The user intent is: *this thing already exists; connect to it*.
- `@app.schedule` and `@app.job` are nouns again, but at least the noun matches the abstraction (a schedule is a schedule).

The inconsistency forces users to memorise each decorator rather than predict it from a rule.

### 3. `InferredPlan` vs `BoundPlan` are jargon-twins

Both end in `Plan`. The compiler-y "inferred" vs "bound" split is meaningful to the framework author but invisible to the user, whose mental model is: *I write code → Skaal figures out what infrastructure I need → Skaal turns that into a deploy plan.* That maps cleanly to **blueprint → plan**, not **inferred-plan → bound-plan**.

The verbs match the same shape: `infer(app)` / `bind(plan, env, lock)` use jargon when **`app.blueprint()`** / **`app.plan(env=...)`** would read as the user-mental-model nouns.

### 4. `ResourceOverride` vs `ResourceOverrides` are *swapped* relative to English

In English, the plural form names a collection of multiple things, and the singular names one of them. The current API has it backwards:

- `ResourceOverrides` (plural-looking) is **one resource's** bag of override fields (`backend`, `options`, …).
- `ResourceOverride` (singular-looking) is **one entry per environment** in `skaal.toml`.

Anyone autocompleting `Resource…` will pick the wrong one half the time.

### 5. The `Backend` namespace has soft duplicates

`Backend`, `BackendEntry`, `BackendConfig`, `BackendCapabilities`. Three of these are runtime-side; one (`BackendEntry`) is registry metadata. "Entry" is meaningless outside that single registry. Either nest (`Backend.Spec`, `Backend.Config`, `Backend.Capabilities`) or rename the registry record to `BackendRegistration` / `BackendSpec`.

### 6. `Target` is overloaded

- `skaal.Target` is the **deploy target** (`aws`, `gcp`, `local`).
- `skaal.api.AppTarget` is a `module:attribute` string **or** a live `App` instance — i.e. *an app reference*.

Same word, two meanings, both in the same surface. `AppTarget` should be `AppRef`; the deploy target stays `Target` (or upgrades to `Cloud` / `Platform`).

### 7. Public verbs in `skaal.api` are uneven

- `api.map` **shadows the Python builtin** `map`. Importing `from skaal import api; api.map(...)` is fine; `from skaal.api import *` is a footgun.
- `api.where` and `api.trace` are single-word cute verbs whose meaning isn't recoverable without docs. `api.locate` and `api.find_source` (or `api.resolve_id`) say what they do.
- The return types `WhereHit` / `TraceHit` use search-engine "hit" jargon. `Location` and `SourceMatch` carry more meaning.
- `StubEmitResult` — "emit" is compiler jargon. `StubsBuilt` or `StubResult` is plain.

### 8. The resilience-policy types don't share a suffix

`RetryPolicy`, `RateLimitPolicy`, `CircuitBreaker`, `Bulkhead`. Half end in `Policy`; half don't. Pick one — most ecosystem libraries drop the suffix (`Retry`, `RateLimit`), and `Bulkhead` / `CircuitBreaker` are industry-standard bare nouns.

### 9. `BeforeInvoke` / `InvokeContext` use the verb instead of the noun

Standard usage is *invocation* (noun) vs *invoke* (verb). `BeforeInvocation` / `InvocationContext` align with how every cloud-runtime SDK names this.

### 10. Module-level loader functions over class methods

`load_environment`, `load_environments`, `load_lock`, `write_lock`, `ensure_relational_schema`, `open_relational_session` are all module-level free functions that operate on a specific class. The Pythonic form is `Environment.load(path)` / `LockFile.load(path)` / `LockFile.save(path)` / `Table.migrate()` / `Table.session()` — the receiver makes the namespace obvious and removes six entries from `__all__`.

### 11. The `__skaal_default_ttl_seconds__` dunder is the wrong escape hatch

A class-level public configuration shouldn't be a private dunder. A normal class attribute (`default_ttl: ClassVar[str] = "30m"`) reads better and is discoverable.

## Proposed rename table

The table below is sequenced from highest-impact-lowest-cost (top) to lowest-impact-higher-cost (bottom). Phase 7 can accept the top section without touching the bottom.

### Resource primitives (high impact, low cost)

| Current | Proposed | Rationale |
|---------|----------|-----------|
| `Relational[T]` | `Table[T]` | Adjective → noun; matches `Store`/`Channel` "the class is the resource"; first-guess discoverability. |
| `Channel[T, B]` | `Topic[T, B]` | Commits to pub/sub semantics — the actually-implemented one. (`Queue` is reserved for `ExternalQueue`'s eventual rename.) |
| `BlobStore[B]` | keep | Renaming to `Blobs` collides with the plural-naming convention users adopt for instances. |
| `BlobObject` | `BlobItem` | Drops the tautology; matches `LockEntry` / `BackendEntry` suffix style. |
| `Store[T, B]` | keep | The one name in the family that already reads cleanly. |

### Decorators (high impact, medium cost — touches every example and docs page)

| Current | Proposed | Rationale |
|---------|----------|-----------|
| `@app.function` | `@app.expose` | Verb of registration matches user intent; stops the "function-decorates-function" tautology. |
| `@app.storage` | keep, but make optional | The class already declares itself via `Store` / `Table` / `BlobStore` / `Topic` base; auto-discovery (`Module.__init_subclass__` walk) lets the decorator become optional. Keep `@app.storage` as the explicit form. |
| `@app.external` | `@app.connect` | Verb of intent ("connect to a pre-existing thing"); pairs with `@app.expose`. |
| `@app.schedule` | keep | Reads cleanly; the noun *is* the abstraction. |
| `@app.job` | keep | Same. |

### Plan / binding layer (medium impact, low cost — internal-ish surface)

| Current | Proposed | Rationale |
|---------|----------|-----------|
| `InferredPlan` | `Blueprint` | Matches user mental model: "what your code says you need". |
| `BoundPlan` | `Plan` | Matches user mental model: "what will deploy". |
| `InferredResource` | `BlueprintResource` | Symmetric with `Blueprint`. |
| `BoundResource` | `PlannedResource` | Symmetric with `Plan`; `Resource` alone is too generic. |
| `ResourceOverrides` | `Overrides` | One resource's override bag; plural form already implies "many fields". |
| `ResourceOverride` | `EnvOverride` | One entry in `skaal.toml` per environment; calls out the scope. |
| `infer(app)` | `app.blueprint()` | Method on `App`; drops a module-level verb. Optional: keep `skaal.blueprint(app)` as the functional form for power users. |
| `bind(plan, env, lock)` | `app.plan(env=...)` | Method on `App`. |
| `BackendEntry` | `BackendSpec` | "Entry" is meaningless out of context. |
| `BackendCapabilities` | keep | Clear and accurate. |
| `BackendConfig` | keep | Clear and accurate. |

### API verbs (medium impact, very low cost — touches CLI parity wrappers + 1–2 docs pages)

| Current | Proposed | Rationale |
|---------|----------|-----------|
| `api.map` | `api.resources` | Stops shadowing the Python builtin. |
| `api.where` | `api.locate` | Says what it does. |
| `api.trace` | `api.find_source` | Says what it does. |
| `WhereHit` | `Location` | Drops search-engine jargon. |
| `TraceHit` | `SourceMatch` | Same. |
| `StubEmitResult` | `StubResult` | Drops "emit" compiler-jargon. |

### Loader functions → classmethods (low impact, low cost — but removes 6 names from `__all__`)

| Current | Proposed | Rationale |
|---------|----------|-----------|
| `load_environment(path)` | `Environment.load(path)` | Receiver-first reads better; one fewer module-level symbol. |
| `load_environments(path)` | `Environment.load_all(path)` | Same. |
| `load_lock(path)` | `LockFile.load(path)` | Same. |
| `write_lock(path, lock)` | `LockFile.save(self, path)` | Same; becomes an instance method. |
| `ensure_relational_schema(table)` | `Table.migrate()` | Classmethod on the new `Table`; matches `Sessions.set(...)` shape. |
| `open_relational_session(table)` | `Table.session()` | Same. |

### Types and contexts (low impact, low cost)

| Current | Proposed | Rationale |
|---------|----------|-----------|
| `BeforeInvoke` | `BeforeInvocation` | Noun, not verb. |
| `InvokeContext` | `InvocationContext` | Same; matches every cloud-runtime SDK. |
| `RetryPolicy` | `Retry` | Drop `Policy` from the two that have it. |
| `RateLimitPolicy` | `RateLimit` | Same. |
| `Bulkhead` / `CircuitBreaker` | keep | Already bare nouns; industry-standard. |
| `AppTarget` (in `skaal.api`) | `AppRef` | Resolves the `Target` collision. |

### Class-level config (low impact, low cost)

| Current | Proposed | Rationale |
|---------|----------|-----------|
| `__skaal_default_ttl_seconds__: ClassVar[float]` | `default_ttl: ClassVar[str \| Duration]` | Public-by-name; accepts the human-readable `"30m"` form already used in `set(..., ttl="45m")`. The inference layer reads the public attribute. |

## Deliberately kept

These names were considered for renaming and rejected:

- **`App`** — three letters, perfectly clear, every framework uses it.
- **`Module`** — same.
- **`Store`** — passes the "predict the next primitive" test once `Topic` and `Table` join it.
- **`BlobStore`** — see above.
- **`Environment`** — industry-standard.
- **`LockFile` / `LockEntry`** — clear and accurate.
- **`ResourceKind`** — clear.
- **`Cron` / `Every`** — concrete, immediately readable.
- **`Schedule` / `ScheduleContext`** — fine.
- **`JobSpec` / `JobHandle` / `JobResult` / `JobStatus`** — consistent suffix family.
- **`SecondaryIndex`** — explicit, no ambiguity.
- **`Page` / `TTL` / `Duration`** — universal.
- **`PluginRegistry` / `Plugin`** (currently `SkaalPlugin`) — drop the `Skaal` prefix on `SkaalPlugin` → `Plugin`; module-namespaced as `skaal.plugins.Plugin`, the brand prefix is redundant. (Listed here because the keep-list is about the *namespace*.)
- **`FunctionRef`** — would become `ExposedFunction` if `@app.function` → `@app.expose` lands. Open question.
- **`SourceLocation` / `SchemaRef` / `Edge`** — `Edge` is mildly jargon-y but the alternative `Dependency` is more loaded. Keep.

## Open questions

1. **Decorator-or-not?** Should `@app.storage` become optional via `__init_subclass__` auto-discovery on `Store` / `Table` / `BlobStore` / `Topic`? If yes, the entire decorator family shrinks to `@app.expose`, `@app.connect`, `@app.schedule`, `@app.job`. If no, keep the current decorator surface.
2. **`Topic` vs `Channel`?** Does Skaal want to commit to pub/sub semantics, or keep `Channel` as a semantic union over pub/sub and work-queue? The runtime only implements one — committing matches the implementation.
3. **`Blueprint` vs `Plan`?** The proposed split (`Blueprint` = inferred, `Plan` = bound) re-uses `Plan` for the *output*, which is the opposite of the current convention (`Plan` is what `skaal plan` produces, which is currently the bound thing — so the convention already matches the proposal). Worth a sanity check.
4. **`app.blueprint()` / `app.plan(env=...)` methods or `skaal.blueprint(app)` / `skaal.plan(app, env)` functions?** Methods are more Pythonic; module-level functions parallel the CLI verbs more cleanly. Could expose both.
5. **`@app.expose` vs `@app.handler`?** `@app.handler` was the deleted Phase 1 name. Reusing it carries baggage but the deleted version meant "HTTP handler", which is exactly the new meaning. Listed as an alternative.

## Sequencing if accepted

If this ADR is accepted, the renames are best landed **before** ADR 035 Phase 7 (the docs / examples rewrite). Sequencing:

1. Mechanical rename pass on `skaal/` — `pyright --strict` + `make test` are the regression gates; both are zero-error today.
2. `skaal/__init__.py` `__all__` re-cut.
3. `notes/redesign-status.md` Phase 7 checklist updated to reference the new names.
4. ADR 035 Phase 7 docs rewrite proceeds against the new vocabulary.

If this ADR is **not** accepted before `v0.4.0`, the renames defer to `v0.5.x` and require a deprecation cycle. The cost of waiting is non-trivial: every doc page, example, stub manifest, and PR-comment template written during Phase 7 cements the current names.

## Decision

Not yet decided. This ADR opens the discussion; the next step is the maintainer reviewing the table and accepting / amending / rejecting the proposed renames before Phase 7 begins.
