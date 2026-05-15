"""AWS-target synth dispatch + stack-walking driver.

`pulumi_program_for(bound, env, build_dir)` (in `skaal.deploy.program`)
returns a closure that invokes `synthesize_stack(...)` from this module.
The driver walks `BoundPlan.resources` in two passes — storage kinds
first, then compute kinds — so every Lambda-shaped synth sees the
upstream storage resources via `ctx.peers` and can wire their env vars
into its container.

This module imports `pulumi`, `pulumi_aws`, and `pulumi_docker` at load
time. Those imports are guarded by `skaal.deploy.program.pulumi_program_for`
which raises a `MissingExtraError` before the closure executes if the
optional extras are not installed; callers should not import this module
directly outside that context.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType

from skaal.binding.model import BoundPlan, BoundResource, Environment
from skaal.deploy.aws import (
    apigw_lambda,
    dynamodb,
    eventbridge,
    lambda_fn,
    postgres,
    redis,
    s3,
    secrets,
    sqs,
    sqs_worker,
)
from skaal.deploy.aws._context import SynthContext, SynthResult
from skaal.deploy.build import _slug_for as _slug_for_resource
from skaal.errors import SkaalDeployError
from skaal.inference.model import ResourceKind

SynthFn = Callable[[SynthContext], SynthResult]


AWS_SYNTH: Mapping[str, SynthFn] = MappingProxyType(
    {
        "dynamodb": dynamodb.synthesize,
        "s3": s3.synthesize,
        "postgres": postgres.synthesize,
        "redis": redis.synthesize,
        "redis-channel": redis.synthesize,
        "sqs": sqs.synthesize,
        "aws-secrets-manager": secrets.synthesize,
        "lambda": lambda_fn.synthesize,
        "apigw-lambda": apigw_lambda.synthesize,
        "eventbridge-lambda": eventbridge.synthesize,
        "sqs-lambda-worker": sqs_worker.synthesize,
    }
)


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


def synthesize_stack(
    bound: BoundPlan, env: Environment, build_dir: Path
) -> dict[str, SynthResult]:
    """Walk `bound.resources` and emit one Pulumi resource set per non-external resource.

    Storage kinds are synthesised first so compute kinds see their env-var
    contributions through `ctx.peers`. Externals are skipped: their
    connection details come from `env.backends[external_name]` and the
    runtime adapter reads them at warm-up.

    Returns:
        Mapping of resource id → `SynthResult` for every resource that
        was synthesised. The driver does not return resources for externals.

    Raises:
        SkaalDeployError: If a resource names a backend that the AWS
            dispatch table does not know — typically a misconfigured
            environment that mixes AWS and GCP backends.
    """
    peers: dict[str, SynthResult] = {}

    _synthesise_pass(bound, env, build_dir, peers, kinds=_STORAGE_KINDS)
    _synthesise_pass(bound, env, build_dir, peers, kinds=_COMPUTE_KINDS)

    return peers


def _synthesise_pass(
    bound: BoundPlan,
    env: Environment,
    build_dir: Path,
    peers: dict[str, SynthResult],
    *,
    kinds: frozenset[ResourceKind],
) -> None:
    """Run one pass of synthesis over the resources whose kind matches."""
    for resource in bound.resources:
        if resource.external:
            continue
        if resource.inferred.kind not in kinds:
            continue
        synth_fn = AWS_SYNTH.get(resource.backend)
        if synth_fn is None:
            raise SkaalDeployError(
                f"No AWS synth module is registered for backend "
                f"{resource.backend!r} (resource {resource.inferred.id!r}). "
                "Check that the env target matches the backend's targets."
            )
        ctx = _context_for(bound, resource, env, build_dir, peers)
        peers[ctx.resource_id] = synth_fn(ctx)


def _context_for(
    bound: BoundPlan,
    resource: BoundResource,
    env: Environment,
    build_dir: Path,
    peers: Mapping[str, SynthResult],
) -> SynthContext:
    """Build the `SynthContext` for one bound resource."""
    return SynthContext(
        bound=bound,
        resource=resource,
        env=env,
        build_dir=build_dir,
        resource_slug=_slug_for_resource(resource),
        peers=peers,
    )


__all__ = [
    "AWS_SYNTH",
    "SynthContext",
    "SynthResult",
    "synthesize_stack",
]
