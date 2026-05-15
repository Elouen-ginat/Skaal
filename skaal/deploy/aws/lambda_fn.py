"""Plain Lambda synth — `aws.lambda_.Function` for `FUNCTION` resources.

Configuration tunables live in `AwsConfig.lambda_defaults`; override via
``[env.<name>.backends.aws.options.lambda_defaults]`` in `skaal.toml`.
Per-resource overrides (``ResourceOverrides.timeout_s`` /
``.memory_mb``) take precedence over the env-level defaults.
"""

from __future__ import annotations

from skaal.deploy._protocol import SynthContext, SynthResult, SynthSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._lambda_common import build_lambda
from skaal.inference.model import ResourceKind

SPEC = SynthSpec(
    backends=("lambda",),
    kinds=frozenset({ResourceKind.FUNCTION}),
    description="AWS Lambda function (image package).",
)


def synthesize(ctx: SynthContext[AwsConfig]) -> SynthResult:
    """Create one container Lambda function for a `FUNCTION` bound resource."""
    overrides = ctx.resource.inferred.overrides
    scaffold = build_lambda(
        ctx,
        timeout=int(overrides.timeout_s) if overrides.timeout_s else None,
        memory_mb=overrides.memory_mb,
    )
    return SynthResult(
        resource_id=ctx.resource_id,
        primary=scaffold.function,
        extras=scaffold.as_extras(),
    )


__all__ = ["SPEC", "synthesize"]
