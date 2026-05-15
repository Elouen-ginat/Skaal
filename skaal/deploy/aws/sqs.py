"""SQS channel synth — `aws.sqs.Queue` per `CHANNEL` bound to `sqs`.

Configuration tunables live in `AwsConfig.sqs`; override via
``[env.<name>.backends.aws.options.sqs]`` in `skaal.toml`.

The `sqs-lambda-worker` JOB backend produces its own queue via
`skaal.deploy.aws.sqs_worker.synthesize`; this module covers the
publisher/subscriber channel form (`Channel[T, Sqs]`) only.
"""

from __future__ import annotations

import pulumi_aws as aws

from skaal.deploy._protocol import SynthContext, SynthResult, SynthSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.inference.model import ResourceKind

SPEC = SynthSpec(
    backends=("sqs",),
    kinds=frozenset({ResourceKind.CHANNEL}),
    description="SQS standard queue for pub/sub channels.",
)


def synthesize(ctx: SynthContext[AwsConfig]) -> SynthResult:
    """Create one SQS queue for a `CHANNEL` bound resource."""
    cfg = ctx.config.sqs
    queue = aws.sqs.Queue(
        ctx.pulumi_name,
        visibility_timeout_seconds=cfg.visibility_timeout_s,
        tags=ctx.tags,
    )
    env_key = f"{cfg.env_var_prefix}{ctx.slug_key}{cfg.env_var_suffix}"
    return SynthResult(
        resource_id=ctx.resource_id,
        primary=queue,
        env_vars={env_key: queue.url},
    )


__all__ = ["SPEC", "synthesize"]
