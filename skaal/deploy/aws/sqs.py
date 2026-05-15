"""SQS channel synth — `aws.sqs.Queue` per `CHANNEL` bound to `sqs`.

Phase 4 emits a vanilla standard queue tagged with the Skaal tag set. The
visibility timeout defaults to AWS's 30-second default and the message
retention defaults to four days; both will become configurable through
`ResourceOverrides.options` in a follow-up.

The `sqs-lambda-worker` JOB backend produces its own queue via
`skaal.deploy.aws.sqs_worker.synthesize`; this module covers the
publisher/subscriber channel form (`Channel[T, Sqs]`) only.
"""

from __future__ import annotations

import pulumi_aws as aws

from skaal.deploy.aws._context import SynthContext, SynthResult


def synthesize(ctx: SynthContext) -> SynthResult:
    """Create one SQS queue for a `CHANNEL` bound resource."""
    queue = aws.sqs.Queue(
        ctx.pulumi_name,
        tags=ctx.tags,
    )
    env_key = f"SKAAL_CHANNEL_{ctx.resource_slug.replace('-', '_').upper()}_URL"
    return SynthResult(
        resource_id=ctx.resource_id,
        primary=queue,
        env_vars={env_key: queue.url},
    )


__all__ = ["synthesize"]
