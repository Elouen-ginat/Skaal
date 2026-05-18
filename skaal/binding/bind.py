"""The pure `bind(plan, env, lock)` function (ADR 028 §6.3, ADR 031 §3.3).

Walks an `InferredPlan` and produces a `BoundPlan` by visiting the four
binding branches in priority order:

1. Type-pin (``InferredResource.overrides.backend`` is set).
2. Lock entry for ``(env.name, res.id)``.
3. Env override in ``env.overrides[res.id]``.
4. Defaults table lookup ``DEFAULTS[res.kind][env.target]``.

After a branch picks a backend the binder validates the choice against
the registry — target reachability, kind coverage — and raises a typed
`SkaalConfigError` if anything is inconsistent. The function is pure: no
side effects, no I/O, no globals beyond the immutable `DEFAULTS` and
`REGISTRY` tables.

Phase 4 (ADR 032 §4.3) carries ``InferredPlan.fingerprint`` through to
``BoundPlan.app_fingerprint`` and computes a separate
``bound_fingerprint`` over the canonical-serialised bound resources.
``BoundResource.external`` is propagated from
``InferredResource.overrides.external``; the type-pin branch is the only
one a `@app.external`-marked resource can enter (un-pinned external is
rejected at decoration time).
"""

from __future__ import annotations

import hashlib
import json

from skaal.binding.model import (
    BackendConfig,
    Environment,
    LockFile,
    Plan,
    PlannedResource,
)
from skaal.binding.registry import BackendSpec, default_entry_for, lookup
from skaal.errors import (
    BackendKindMismatch,
    BackendNotAvailableForTarget,
    TypePinViolation,
)
from skaal.inference.model import Blueprint, BlueprintResource


def plan(plan: Blueprint, env: Environment, lock: LockFile) -> Plan:
    """Bind every resource in ``plan`` to one concrete backend.

    Args:
        plan: The deterministic, environment-independent inference output.
        env: The active environment from `skaal.toml`.
        lock: The pin-on-first-deploy state from `skaal.lock`.

    Returns:
        A `BoundPlan` with one `BoundResource` per inferred resource, the
        original edges carried through unchanged, the inference
        fingerprint copied into ``app_fingerprint``, and a
        ``bound_fingerprint`` covering the post-binding choices.

    Raises:
        TypePinViolation: An override repointed a type-pinned resource.
        BackendKindMismatch: The chosen backend cannot host the resource's kind.
        BackendNotAvailableForTarget: The backend is not deployable on the env's target.
        UnknownBackendError: A string in the env or lock did not resolve to a token.
    """
    bound = tuple(_bind_resource(res, env, lock) for res in plan.resources)
    skeleton = Plan(
        app=plan.app,
        environment=env.name,
        resources=bound,
        edges=plan.edges,
        app_fingerprint=plan.fingerprint,
    )
    return skeleton.model_copy(update={"bound_fingerprint": _bound_fingerprint(skeleton)})


def _bound_fingerprint(plan: Plan) -> str:
    """Compute the 16-hex-char fingerprint of ``plan`` (excluding itself)."""
    data = plan.model_dump(
        mode="json",
        by_alias=True,
        # `pinned` reflects whether the lock already matches this binding, not
        # the binding choice itself, so it must not perturb the plan fingerprint.
        exclude={"bound_fingerprint": True, "resources": {"__all__": {"pinned"}}},
    )
    data["resources"] = sorted(data["resources"], key=lambda r: (r["backend"], r["inferred"]["id"]))
    data["edges"] = sorted(data["edges"], key=lambda e: (e["source_id"], e["target_id"], e["kind"]))
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:16]


def _bind_resource(res: BlueprintResource, env: Environment, lock: LockFile) -> PlannedResource:
    pinned_backend = res.overrides.backend
    lock_entry = lock.entries.get((env.name, res.id))
    env_override = env.overrides.get(res.id)

    if pinned_backend is not None:
        if lock_entry is not None and lock_entry.backend != pinned_backend:
            raise TypePinViolation(res.id, pinned_backend, lock_entry.backend)
        if env_override is not None and env_override.backend != pinned_backend:
            raise TypePinViolation(res.id, pinned_backend, env_override.backend)
        entry = lookup(pinned_backend)
        _validate(entry, res, env)
        return _build(res, entry, env, pinned=True)

    if res.overrides.external:
        # `@app.external` without a type-pin is rejected at decoration time;
        # reaching here means the inferred resource was hand-built. Surface
        # the same error so the binder is self-consistent.
        raise TypePinViolation(
            res.id,
            "<unpinned>",
            "external resources must declare a backend type-pin",
        )

    if lock_entry is not None:
        entry = lookup(lock_entry.backend)
        _validate(entry, res, env)
        return _build(
            res,
            entry,
            env,
            pinned=True,
            region=lock_entry.region,
        )

    if env_override is not None:
        entry = lookup(env_override.backend)
        _validate(entry, res, env)
        return _build(
            res,
            entry,
            env,
            pinned=False,
            region=env_override.region,
            options=env_override.options,
        )

    entry = default_entry_for(res.kind, env.target)
    _validate(entry, res, env)
    return _build(res, entry, env, pinned=False)


def _validate(entry: BackendSpec, res: BlueprintResource, env: Environment) -> None:
    if env.target not in entry.targets:
        raise BackendNotAvailableForTarget(entry.token_class.name, env.target.value)
    if res.kind.value not in entry.token_class.kinds:
        raise BackendKindMismatch(res.id, entry.token_class.name, res.kind.value)


def _build(
    res: BlueprintResource,
    entry: BackendSpec,
    env: Environment,
    *,
    pinned: bool,
    region: str | None = None,
    options: dict[str, str] | None = None,
) -> PlannedResource:
    external = res.overrides.external
    external_name = res.overrides.external_name
    backend_config: BackendConfig | None
    if external and external_name is not None:
        backend_config = env.backends.get(external_name) or env.backends.get(entry.token_class.name)
    else:
        backend_config = env.backends.get(entry.token_class.name)
    return PlannedResource(
        inferred=res,
        backend=entry.token_class.name,
        region=region if region is not None else env.region,
        options=dict(options or {}),
        backend_config=backend_config,
        pinned=pinned,
        external=external,
        external_name=external_name,
    )
