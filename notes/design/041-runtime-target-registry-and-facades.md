# ADR 041 — Runtime target registry and target-first packages

**Status:** Proposed
**Date:** 2026-05-17
**Related:** [ADR 032](032-runtime-deploy-on-bound-plan-implementation-plan.md) §4.1 and §4.12; [ADR 038](038-lambda-cold-start-backend-wiring.md)
**Phase:** ADR 028 §9.4 (Phase 4 follow-through)
**Target alpha tag:** `v0.4.0-alpha.7`

---

## Goal

Keep runtime growth on the same architectural path as deploy and binding: one registry-backed extension seam, target-first packages, and no target-selection or backend-selection `if` / `elif` chains in shared runtime modules.

This ADR records the boundary introduced by the runtime-registry slice:

- `skaal.runtime._registry` owns runtime target registration and lookup.
- `skaal.runtime.<target>` owns target-specific bootstrap, backend factories, wire hooks, and local-only helpers.
- shared runtime modules stay narrow; target growth happens under the target package itself.

## Decision 1 — Runtime extensibility is target-first

The unit of extension is a named runtime target, not a new branch in a shared dispatcher.

Each runtime target contributes three independent maps:

- local-runtime kind adapters keyed by `ResourceKind`
- deploy-managed binding wirers keyed by `ResourceKind`
- backend factories keyed by `(ResourceKind, backend_name)`

That split matters because local runtime and cold-start runtime do not share the same lifecycle. A local adapter may register routes and startup hooks; an AWS wirer only binds pre-provisioned resources onto already-declared primitives. They need one registry, but not one callable shape.

## Decision 2 — Runtime packages own their target logic

`skaal.runtime.aws` remains the stable import surface used by generated bootstraps, and it is also the ownership boundary for AWS runtime code. The same applies to `skaal.runtime.local` for the in-process runtime.

This is the rule for future runtime targets as well:

- `skaal.runtime.<target>` is the stable import surface and the owning package.
- target-specific submodules such as `bootstrap`, `target`, `dispatch`, `middleware`, or `backends` live under that package.

This keeps the runtime package coherent without reintroducing flat shared modules that only forward imports.

## Decision 3 — Plugin hooks extend the same registry

Plugins do not get a separate runtime plugin API. They extend the same runtime target registry through `skaal.plugins.PluginRegistry`.

The supported contribution shapes are:

- `add_runtime_target(...)`
- `add_runtime_adapter(...)`
- `add_runtime_binding_wirer(...)`
- `add_runtime_backend_factory(...)`

That keeps third-party runtime growth aligned with the in-tree pattern already used by deploy targets and binding backends.

## Consequences

Positive:

- adding a runtime target no longer requires editing shared `dispatch.py`-style conditionals
- target-specific code lives together under one package instead of being split between a public module and a hidden `targets/` directory
- plugin-contributed runtimes follow the same registration story as plugin-contributed deploy targets

Tradeoff:

- runtime behavior is spread across the registry plus target packages, so debugging starts with lookup paths instead of one flat file. This is acceptable because the extension seam is explicit and testable.

## Exit criteria

- [ ] `skaal.runtime.local.dispatch` resolves the local adapter through the runtime registry
- [ ] `skaal.runtime.aws` owns the AWS cold-start runtime package
- [ ] `skaal.plugins.PluginRegistry` exposes runtime-target contribution hooks
- [ ] focused runtime and plugin tests cover the registry lookup path
