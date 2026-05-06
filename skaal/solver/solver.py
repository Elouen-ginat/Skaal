"""Main solve() entry point — orchestrates storage, compute, component, and pattern solvers."""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from skaal.plan import ComponentSpec, ComputeSpec, PatternSpec, PlanFile, StorageSpec
from skaal.solver._pattern_solvers import PatternSolveContext, collect_function_names, solve_pattern
from skaal.solver.graph import CyclicDependencyError, build_graph
from skaal.solver.storage import select_backend
from skaal.solver.targets import catalog_compute_key
from skaal.types.patterns import PatternMetadata

if TYPE_CHECKING:
    from skaal.app import App


log = logging.getLogger("skaal.solver")


def _compute_schema_hash(obj: Any) -> str:
    """
    Compute a stable hash of a class schema from its annotations.

    This hash changes when fields are added, removed, or their types change,
    enabling proper schema migration detection.

    Args:
        obj: The class object to hash.

    Returns:
        A 12-character hex string (first 12 chars of SHA256).
    """
    # Collect all annotations from the class and its bases
    annotations: dict[str, str] = {}
    for base in reversed(inspect.getmro(obj)):
        if base is object:
            continue
        base_annotations = getattr(base, "__annotations__", {})
        for field_name, field_type in base_annotations.items():
            # Normalize type annotations to string
            if hasattr(field_type, "__module__") and hasattr(field_type, "__qualname__"):
                type_str = f"{field_type.__module__}.{field_type.__qualname__}"
            else:
                type_str = str(field_type)
            annotations[field_name] = type_str

    # Sort for stability and JSON-encode
    if not annotations:
        # No annotations; fall back to qualname
        qname = getattr(obj, "__module__", "") + "." + getattr(obj, "__qualname__", "Unknown")
        payload = qname.encode()
    else:
        payload = json.dumps(annotations, sort_keys=True, default=str).encode()

    return hashlib.sha256(payload).hexdigest()[:12]


# ── Helpers for serialising resilience dataclasses ────────────────────────────


def _policy_to_dict(policy: Any) -> dict[str, Any] | None:
    """Serialise a resilience policy dataclass to a plain dict (JSON-safe)."""
    if policy is None:
        return None
    if dataclasses.is_dataclass(policy) and not isinstance(policy, type):
        return dataclasses.asdict(policy)
    # Fallback: assume a dict-ish payload
    return dict(policy) if isinstance(policy, Mapping) else None


def _collect_all_components(app: App) -> dict[str, Any]:
    """
    Recursively collect all components from *app* and every mounted submodule.

    Components are not included in ``_collect_all()`` (which only yields
    storage/agents/functions/channels/patterns/schedules).  This helper fills
    that gap so the solver can plan components declared inside modules that are
    mounted into the app via ``app.use()``.
    """
    result: dict[str, Any] = {}

    def _recurse(module: Any) -> None:
        for name, comp in getattr(module, "_components", {}).items():
            if name not in result:  # top-level wins on name collision
                result[name] = comp
        for sub in getattr(module, "_submodules", {}).values():
            _recurse(sub)

    _recurse(app)
    return result


def solve(app: App, catalog: dict[str, Any], target: str = "generic") -> PlanFile:
    """
    Run the Z3 constraint solver over all registered storage and compute
    declarations, producing a concrete infrastructure plan.

    Args:
        app:     The Skaal App whose decorators define the constraints.
        catalog: Parsed TOML catalog entries (backends and their characteristics).
        target:  Deploy target: "generic" | "aws-lambda" | "k8s" | "ecs"

    Returns:
        A PlanFile with concrete backend and instance selections.

    Raises:
        UnsatisfiableConstraints: If no backend can satisfy the declared constraints.
    """
    all_resources = app._collect_all()
    storage_backends = catalog.get("storage", {})
    compute_backends = catalog.get("compute", {})

    storage_specs: dict[str, StorageSpec] = {}
    compute_specs: dict[str, ComputeSpec] = {}
    component_specs: dict[str, ComponentSpec] = {}
    pattern_specs: dict[str, PatternSpec] = {}

    # ── Dependency graph ──────────────────────────────────────────────────
    # Build once up front so every sub-solver can consult it.  The ordering is
    # written into the plan so deploy generators can provision resources in
    # dependency order.
    graph = build_graph(app)
    try:
        resource_order = graph.topological_order()
    except CyclicDependencyError as exc:
        log.warning(
            f"Cyclic dependency detected in resource graph: {exc}. "
            "Falling back to unordered resource list."
        )
        resource_order = sorted(all_resources.keys())

    # ── Solve storage ──────────────────────────────────────────────────────
    for qname, obj in all_resources.items():
        if not (isinstance(obj, type) and hasattr(obj, "__skaal_storage__")):
            continue

        constraints = obj.__skaal_storage__

        backend_name, reason = select_backend(
            qname,
            constraints,
            storage_backends,
            target=target,
        )

        # Compute a stable schema hash from the class's annotated fields
        # This changes when fields are added, removed, or their types change
        schema_hash = _compute_schema_hash(obj)

        # Carry deploy-time provisioning params from the catalog into the plan.
        # The solver never reads these; they are only consumed by deploy generators.
        backend_entry = storage_backends.get(backend_name, {})
        deploy_params = backend_entry.get("deploy", {})
        wire_params = backend_entry.get("wire", {})

        # Resolve collocate_with: the decorator takes a raw string which may
        # be a bare class name or a qualified name.  Normalise to a qualified
        # name if it resolves against a registered resource.
        raw_colocate = constraints.get("collocate_with")
        colocate_qname: str | None = None
        if raw_colocate:
            if raw_colocate in all_resources:
                colocate_qname = raw_colocate
            else:
                for candidate in all_resources:
                    if candidate == raw_colocate or candidate.endswith(f".{raw_colocate}"):
                        colocate_qname = candidate
                        break
                if colocate_qname is None:
                    log.warning(
                        f"Storage {qname!r}: collocate_with={raw_colocate!r} "
                        "does not match any registered resource. Ignored."
                    )

        storage_specs[qname] = StorageSpec(
            variable_name=qname,
            backend=backend_name,
            kind=constraints.get("kind", "kv"),
            previous_backend=None,
            migration_plan=None,
            migration_stage=0,
            schema_hash=schema_hash,
            reason=reason,
            collocate_with=colocate_qname,
            auto_optimize=bool(constraints.get("auto_optimize", False)),
            deploy_params=deploy_params,
            wire_params=wire_params,
        )

    # ── Solve compute ──────────────────────────────────────────────────────
    from skaal.solver.compute import UnsatisfiableComputeConstraints, encode_compute

    for qname, obj in all_resources.items():
        if not (callable(obj) and hasattr(obj, "__skaal_compute__")):
            continue

        compute_constraint = obj.__skaal_compute__
        try:
            instance_type, reason = encode_compute(
                qname, compute_constraint, compute_backends, target=target
            )
        except UnsatisfiableComputeConstraints as e:
            # Warn the user that their constraint was violated, then fall back to cheapest
            log.warning(
                f"Compute constraint for {qname!r} is unsatisfiable: {e}. "
                "Falling back to cheapest available instance."
            )
            if compute_backends:
                instance_type = min(
                    compute_backends, key=lambda n: compute_backends[n].get("cost_per_hour", 9999)
                )
                reason = f"fallback: cheapest available ({instance_type})"
            else:
                instance_type = "c5-large"
                reason = "default compute (empty catalog)"

        # Resolve collocate_with on the compute object
        raw_colocate = getattr(compute_constraint, "collocate_with", None)
        colocate_qname = None
        if raw_colocate:
            if raw_colocate in all_resources:
                colocate_qname = raw_colocate
            else:
                for candidate in all_resources:
                    if candidate == raw_colocate or candidate.endswith(f".{raw_colocate}"):
                        colocate_qname = candidate
                        break
                if colocate_qname is None:
                    log.warning(
                        f"Function {qname!r}: collocate_with={raw_colocate!r} "
                        "does not match any registered resource. Ignored."
                    )

        # Scale strategy — set by @scale decorator
        scale_obj = getattr(obj, "__skaal_scale__", None)
        scale_strategy: str | None = None
        instances: int | str = "auto"
        if scale_obj is not None:
            strategy = getattr(scale_obj, "strategy", None)
            if strategy is not None:
                scale_strategy = strategy.value if hasattr(strategy, "value") else str(strategy)
            instances = getattr(scale_obj, "instances", "auto")

        compute_specs[qname] = ComputeSpec(
            function_name=qname,
            instance_type=instance_type,
            instances=instances,
            previous_instance_type=None,
            reason=reason,
            collocate_with=colocate_qname,
            scale_strategy=scale_strategy,
            retry=_policy_to_dict(getattr(compute_constraint, "retry", None)),
            circuit_breaker=_policy_to_dict(getattr(compute_constraint, "circuit_breaker", None)),
            rate_limit=_policy_to_dict(getattr(compute_constraint, "rate_limit", None)),
            bulkhead=_policy_to_dict(getattr(compute_constraint, "bulkhead", None)),
        )

    # ── Solve components ───────────────────────────────────────────────────
    from skaal.components import ComponentBase
    from skaal.solver.components import encode_component

    for comp_name, comp_obj in _collect_all_components(app).items():
        if isinstance(comp_obj, ComponentBase):
            try:
                spec = encode_component(comp_name, comp_obj, catalog, target=target)
                component_specs[comp_name] = spec
            except Exception as exc:
                log.warning(
                    f"Component {comp_name!r} encoding failed: {exc}. "
                    "It will be omitted from the plan."
                )

    # ── Solve patterns (EventLog, Projection, Saga, Outbox) ───────────────
    registered_functions = collect_function_names(app)

    for qname, obj in all_resources.items():
        if not hasattr(obj, "__skaal_pattern__"):
            continue
        pattern_meta = obj.__skaal_pattern__
        if not isinstance(pattern_meta, dict) or "pattern_type" not in pattern_meta:
            continue

        pattern_spec = solve_pattern(
            PatternSolveContext(
                qname=qname,
                pattern_meta=cast(PatternMetadata, pattern_meta),
                all_resources=all_resources,
                storage_specs=storage_specs,
                storage_backends=storage_backends,
                registered_functions=registered_functions,
                target=target,
            )
        )
        if pattern_spec is not None:
            pattern_specs[qname] = pattern_spec

    # ── Propagate collocation through the storage graph ───────────────────
    # A storage that is co-located with another storage inherits the region /
    # cluster hints of its target.  We cannot enforce region pinning here
    # (that's a deploy-time concern), but we can surface the inherited target
    # in the plan so downstream generators can follow the chain in one pass.
    _propagate_collocation(storage_specs, compute_specs, resource_order)

    # ── Target-level deploy config ─────────────────────────────────────────
    # Read the deploy params for the target compute backend (e.g. Lambda,
    # Cloud Run) from the catalog.  The solver doesn't use these; deploy
    # generators do.
    target_compute_key = catalog_compute_key(target)
    deploy_config: dict[str, Any] = {}
    if target_compute_key:
        deploy_config = compute_backends.get(target_compute_key, {}).get("deploy", {})

    secret_specs = {name: ref.to_spec() for name, ref in app._collect_secrets().items()}

    return PlanFile(
        app_name=app.name,
        version=1,
        previous_version=None,
        deploy_target=target,
        deploy_config=deploy_config,
        storage=storage_specs,
        compute=compute_specs,
        components=component_specs,
        patterns=pattern_specs,
        secrets=secret_specs,
        resource_order=resource_order,
    )


def _propagate_collocation(
    storage_specs: dict[str, StorageSpec],
    compute_specs: dict[str, ComputeSpec],
    order: list[str],
) -> None:
    """
    Walk the resource graph in topological order and flatten transitive
    ``collocate_with`` chains.

    If ``A → B → C`` (A depends on B depends on C), rewrite A's
    ``collocate_with`` to point to the root of its chain (C), so deploy
    generators can group co-located resources without walking the graph.
    """

    def _root(qname: str, seen: set[str]) -> str:
        if qname in seen:  # cycle guard, the graph builder has already warned
            return qname
        seen.add(qname)
        nxt: str | None = None
        if qname in storage_specs:
            nxt = storage_specs[qname].collocate_with
        elif qname in compute_specs:
            nxt = compute_specs[qname].collocate_with
        if nxt is None or nxt == qname:
            return qname
        return _root(nxt, seen)

    for qname in order:
        if qname in storage_specs and storage_specs[qname].collocate_with:
            root = _root(storage_specs[qname].collocate_with or "", set())
            if root and root != storage_specs[qname].collocate_with:
                storage_specs[qname] = storage_specs[qname].model_copy(
                    update={"collocate_with": root}
                )
        if qname in compute_specs and compute_specs[qname].collocate_with:
            root = _root(compute_specs[qname].collocate_with or "", set())
            if root and root != compute_specs[qname].collocate_with:
                compute_specs[qname] = compute_specs[qname].model_copy(
                    update={"collocate_with": root}
                )
