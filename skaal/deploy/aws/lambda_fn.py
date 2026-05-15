"""Plain Lambda synth — `aws.lambda_.Function` for `FUNCTION` resources.

The function-kind Lambda has no event source attached at this layer. It
is invoked directly (e.g. by another Lambda, by SDK callers, or via a
follow-up API Gateway route added through the `apigw-lambda` backend on
an `ASGI_SERVICE`). Phase 4 ships timeout / memory at the framework
defaults; `ResourceOverrides.timeout_s` / `.memory_mb` plumbing lands in
a follow-up.
"""

from __future__ import annotations

from skaal.deploy.aws._context import SynthContext, SynthResult
from skaal.deploy.aws._lambda_common import build_lambda


def synthesize(ctx: SynthContext) -> SynthResult:
    """Create one container Lambda function for a `FUNCTION` bound resource."""
    overrides = ctx.resource.inferred.overrides
    scaffold = build_lambda(
        ctx,
        timeout=int(overrides.timeout_s) if overrides.timeout_s else 30,
        memory_mb=overrides.memory_mb or 512,
    )
    return SynthResult(
        resource_id=ctx.resource_id,
        primary=scaffold.function,
        extras=scaffold.as_extras(),
    )


__all__ = ["synthesize"]
