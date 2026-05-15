"""SQS + Lambda worker synth — `JOB` resources backed by `sqs-lambda-worker`.

Configuration tunables live in `AwsConfig.lambda_defaults` (timeout,
visibility timeout, batch size); override via
``[env.<name>.backends.aws.options.lambda_defaults]`` in `skaal.toml`.
"""

from __future__ import annotations

import pulumi_aws as aws

from skaal.deploy._protocol import SynthContext, SynthResult, SynthSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._lambda_common import build_lambda
from skaal.inference.model import ResourceKind

SPEC = SynthSpec(
    backends=("sqs-lambda-worker",),
    kinds=frozenset({ResourceKind.JOB}),
    description="SQS queue + Lambda worker (event-source mapping).",
)


def synthesize(ctx: SynthContext[AwsConfig]) -> SynthResult:
    """Create an SQS-driven Lambda worker for a `JOB` bound resource."""
    cfg = ctx.config
    queue = aws.sqs.Queue(
        f"{ctx.pulumi_name}-queue",
        visibility_timeout_seconds=cfg.lambda_defaults.job_visibility_timeout_s,
        tags=ctx.tags,
    )
    queue_env_key = f"SKAAL_JOB_{ctx.slug_key}_URL"
    overrides = ctx.resource.inferred.overrides
    scaffold = build_lambda(
        ctx,
        timeout=(
            int(overrides.timeout_s)
            if overrides.timeout_s
            else cfg.lambda_defaults.job_timeout_s
        ),
        memory_mb=overrides.memory_mb,
        extra_env={queue_env_key: queue.url},
    )

    if "sqs" in cfg.iam.policies:
        aws.iam.RolePolicyAttachment(
            f"{ctx.pulumi_name}-sqs-consume",
            role=scaffold.role.name,
            policy_arn=cfg.iam.policies["sqs"],
        )
    mapping = aws.lambda_.EventSourceMapping(
        f"{ctx.pulumi_name}-mapping",
        event_source_arn=queue.arn,
        function_name=scaffold.function.name,
        batch_size=cfg.lambda_defaults.job_batch_size,
    )

    return SynthResult(
        resource_id=ctx.resource_id,
        primary=scaffold.function,
        extras=(*scaffold.as_extras(), queue, mapping),
        env_vars={queue_env_key: queue.url},
    )


__all__ = ["SPEC", "synthesize"]
