"""`pulumi_program_for(bound, env, build_dir)` — the deploy-side entry point.

The Pulumi Automation API expects a parameterless callable that runs
inside its stack context. `pulumi_program_for` returns that callable as a
closure capturing `bound`, `env`, and the `build_dir` produced by
`build_artefacts(...)`.

The closure does *not* hardcode any cloud target. It asks the registry
for the `DeployTarget` matching `env.target` and dispatches through that
target's `lookup_synth(...)` method. A new target plugs in by:

1. Creating `skaal/deploy/<target>/` with one `SynthModule` subclass per
   backend (Lambda-shaped synths inherit from `LambdaSynth`)
2. Constructing a `BaseDeployTarget` subclass via `from_classes(...)`
   and calling `register_target(...)` at module import time
3. Importing the new target package so registration runs

The `pulumi` / `pulumi_aws` / `pulumi_docker` imports are deferred until
the closure is *invoked*. Building the closure itself works without the
optional extras installed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from skaal.binding.model import BoundPlan, BoundResource, Environment
from skaal.deploy._protocol import SynthContext, SynthResult, TargetConfig
from skaal.deploy._registry import get_target
from skaal.deploy.build import _slug_for as _slug_for_resource
from skaal.errors import MissingExtraError, SkaalDeployError
from skaal.inference.model import ResourceKind

PulumiProgram = Callable[[], None]


_STORAGE_KINDS: frozenset[ResourceKind] = frozenset(
    {
        ResourceKind.STORE,
        ResourceKind.RELATIONAL,
        ResourceKind.BLOB,
        ResourceKind.CHANNEL,
        ResourceKind.SECRET,
    }
)

_COMPUTE_KINDS: frozenset[ResourceKind] = frozenset(
    {
        ResourceKind.FUNCTION,
        ResourceKind.ASGI_SERVICE,
        ResourceKind.SCHEDULE,
        ResourceKind.JOB,
    }
)


def pulumi_program_for(bound: BoundPlan, env: Environment, build_dir: Path) -> PulumiProgram:
    """Return a parameterless Pulumi program callable for `bound`.

    Args:
        bound: The bound plan whose resources will be provisioned.
        env: The active environment. `env.target` picks the deploy
            target via the registry.
        build_dir: The directory `build_artefacts(...)` wrote to. Each
            compute synth uses ``build_dir / <resource_slug>`` as its
            Docker build context.

    Returns:
        A callable Pulumi can invoke inside its stack context.
    """

    def program() -> None:
        # Import the target package eagerly so it registers itself.
        _import_target_package(env)
        target = get_target(env.target)
        _require_extras(target.required_extras())
        synthesize_stack(bound, env, build_dir)

    return program


def synthesize_stack(bound: BoundPlan, env: Environment, build_dir: Path) -> dict[str, SynthResult]:
    """Walk `bound.resources` and dispatch each through `env.target`'s synths.

    Storage kinds synthesize before compute kinds so each compute synth
    sees its upstream storage peers via `ctx.peers`. Externals are
    skipped: their connection details come from
    `env.backends[external_name]` and the runtime adapter reads them at
    warm-up.

    Returns:
        Mapping of resource id → `SynthResult` for every resource that
        was synthesised. The driver does not include externals.

    Raises:
        SkaalDeployError: If a resource names a backend that the target
            does not know how to synthesise.
    """
    target = get_target(env.target)
    target_config = target.config_for(env)
    peers: dict[str, SynthResult] = {}

    _synthesise_pass(bound, env, build_dir, peers, target_config, kinds=_STORAGE_KINDS)
    _synthesise_pass(bound, env, build_dir, peers, target_config, kinds=_COMPUTE_KINDS)

    return peers


def _synthesise_pass(
    bound: BoundPlan,
    env: Environment,
    build_dir: Path,
    peers: dict[str, SynthResult],
    config: TargetConfig,
    *,
    kinds: frozenset[ResourceKind],
) -> None:
    target = get_target(env.target)
    for resource in bound.resources:
        if resource.external or resource.inferred.kind not in kinds:
            continue
        synth_fn = target.lookup_synth(resource.backend)
        if synth_fn is None:
            raise SkaalDeployError(
                f"Target {env.target.value!r} has no synth registered for "
                f"backend {resource.backend!r} (resource "
                f"{resource.inferred.id!r}). Registered backends: "
                f"{', '.join(sorted(target.supported_backends())) or '(none)'}."
            )
        ctx = _context_for(bound, resource, env, build_dir, peers, config)
        peers[ctx.resource_id] = synth_fn(ctx)


def _context_for(
    bound: BoundPlan,
    resource: BoundResource,
    env: Environment,
    build_dir: Path,
    peers: Mapping[str, SynthResult],
    config: TargetConfig,
) -> SynthContext[TargetConfig]:
    return SynthContext(
        bound=bound,
        resource=resource,
        env=env,
        build_dir=build_dir,
        resource_slug=_slug_for_resource(resource),
        peers=peers,
        config=config,
    )


def _import_target_package(env: Environment) -> None:
    """Best-effort import of the per-target package so it self-registers.

    The registry is populated by the side effect of importing
    `skaal.deploy.<target>`. We map each `Target` enum value to a
    package path so the program callable can trigger registration on
    demand instead of forcing the whole CLI to import every target's
    optional extras upfront.
    """
    package = f"skaal.deploy.{env.target.value}"
    try:
        __import__(package)
    except ImportError as exc:
        raise MissingExtraError(
            f"Could not import deploy target {env.target.value!r} "
            f"(`{package}`). Install the matching optional extras "
            "(e.g. `pip install 'skaal[deploy,aws]'`)."
        ) from exc


def _require_extras(extras: tuple[str, ...]) -> None:
    """Verify every required-extra module is importable."""
    missing: list[str] = []
    for module in extras:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        raise MissingExtraError(
            "`skaal deploy` requires additional SDKs. Install them with "
            "`pip install 'skaal[deploy,aws]'` "
            f"(missing modules: {', '.join(missing)})."
        )


__all__ = ["PulumiProgram", "pulumi_program_for", "synthesize_stack"]
