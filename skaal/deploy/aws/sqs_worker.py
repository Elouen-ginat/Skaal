"""SQS + Lambda worker synth — `JOB` resources backed by `sqs-lambda-worker`.

Builds the standard Lambda scaffold and pairs it with a dedicated SQS
queue plus an event-source mapping so the Lambda consumes batches off the
queue. The queue URL is exported as ``SKAAL_JOB_<slug>_URL`` so any
publisher in the same stack can write to it directly.
"""

from __future__ import annotations

import pulumi_aws as aws

from skaal.deploy.aws._context import SynthContext, SynthResult
from skaal.deploy.aws._lambda_common import build_lambda


def synthesize(ctx: SynthContext) -> SynthResult:
    """Create an SQS-driven Lambda worker for a `JOB` bound resource."""
    queue = aws.sqs.Queue(
        f"{ctx.pulumi_name}-queue",
        visibility_timeout_seconds=120,
        tags=ctx.tags,
    )
    slug_key = ctx.resource_slug.replace("-", "_").upper()
    overrides = ctx.resource.inferred.overrides
    scaffold = build_lambda(
        ctx,
        timeout=int(overrides.timeout_s) if overrides.timeout_s else 60,
        memory_mb=overrides.memory_mb or 512,
        extra_env={f"SKAAL_JOB_{slug_key}_URL": queue.url},
    )

    aws.iam.RolePolicyAttachment(
        f"{ctx.pulumi_name}-sqs-consume",
        role=scaffold.role.name,
        policy_arn="arn:aws:iam::aws:policy/AmazonSQSFullAccess",
    )
    mapping = aws.lambda_.EventSourceMapping(
        f"{ctx.pulumi_name}-mapping",
        event_source_arn=queue.arn,
        function_name=scaffold.function.name,
        batch_size=10,
    )

    return SynthResult(
        resource_id=ctx.resource_id,
        primary=scaffold.function,
        extras=(*scaffold.as_extras(), queue, mapping),
        env_vars={f"SKAAL_JOB_{slug_key}_URL": queue.url},
    )


__all__ = ["synthesize"]
