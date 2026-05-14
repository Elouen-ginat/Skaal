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
"""

from __future__ import annotations

from skaal.binding.defaults import DEFAULTS
from skaal.binding.model import (
    BackendConfig,
    BoundPlan,
    BoundResource,
    Environment,
    LockFile,
)
from skaal.binding.registry import BackendEntry, lookup
from skaal.errors import (
    BackendKindMismatch,
    BackendNotAvailableForTarget,
    TypePinViolation,
)
from skaal.inference.model import InferredPlan, InferredResource


def bind(plan: InferredPlan, env: Environment, lock: LockFile) -> BoundPlan:
    """Bind every resource in ``plan`` to one concrete backend.

    Args:
        plan: The deterministic, environment-independent inference output.
        env: The active environment from `skaal.toml`.
        lock: The pin-on-first-deploy state from `skaal.lock`.

    Returns:
        A `BoundPlan` with one `BoundResource` per inferred resource and
        the original edges carried through unchanged.

    Raises:
        TypePinViolation: An override repointed a type-pinned resource.
        BackendKindMismatch: The chosen backend cannot host the resource's kind.
        BackendNotAvailableForTarget: The backend is not deployable on the env's target.
        UnknownBackendError: A string in the env or lock did not resolve to a token.
    """
    bound = tuple(_bind_resource(res, env, lock) for res in plan.resources)
    return BoundPlan(
        app=plan.app,
        environment=env.name,
        resources=bound,
        edges=plan.edges,
    )


def _bind_resource(
    res: InferredResource, env: Environment, lock: LockFile
) -> BoundResource:
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

    token = DEFAULTS[res.kind][env.target]
    entry = lookup(token.name)
    _validate(entry, res, env)
    return _build(res, entry, env, pinned=False)


def _validate(entry: BackendEntry, res: InferredResource, env: Environment) -> None:
    if env.target not in entry.targets:
        raise BackendNotAvailableForTarget(entry.token.name, env.target.value)
    if res.kind.value not in entry.token.kinds:
        raise BackendKindMismatch(res.id, entry.token.name, res.kind.value)


def _build(
    res: InferredResource,
    entry: BackendEntry,
    env: Environment,
    *,
    pinned: bool,
    region: str | None = None,
    options: dict[str, str] | None = None,
) -> BoundResource:
    backend_config: BackendConfig | None = env.backends.get(entry.token.name)
    return BoundResource(
        inferred=res,
        backend=entry.token.name,
        region=region if region is not None else env.region,
        options=dict(options or {}),
        backend_config=backend_config,
        pinned=pinned,
    )
