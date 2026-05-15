"""SQS + Lambda worker synth class — `JOB` resources.

Builds a queue first so the queue URL can be injected into the Lambda's
env vars, then the standard Lambda scaffold with that extra env, then an
event-source mapping to wire the queue to the Lambda. Configuration
tunables live in `AwsConfig.lambda_defaults` (timeout / visibility
timeout / batch size).
"""

from __future__ import annotations

from typing import ClassVar

import pulumi_aws as aws

from skaal.deploy._protocol import SynthContext, SynthResult, SynthSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._lambda import LambdaSynth
from skaal.inference.model import ResourceKind


class SqsWorkerSynth(LambdaSynth):
    """SQS queue + Lambda worker (event-source mapping)."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        backends=("sqs-lambda-worker",),
        kinds=frozenset({ResourceKind.JOB}),
        description="SQS queue + Lambda worker (event-source mapping).",
    )

    def _timeout_s(self, ctx: SynthContext[AwsConfig]) -> int:
        overrides = ctx.resource.inferred.overrides
        if overrides.timeout_s:
            return int(overrides.timeout_s)
        return ctx.config.lambda_defaults.job_timeout_s

    def synthesize(self, ctx: SynthContext[AwsConfig]) -> SynthResult:
        cfg = ctx.config
        queue = aws.sqs.Queue(
            f"{ctx.pulumi_name}-queue",
            visibility_timeout_seconds=cfg.lambda_defaults.job_visibility_timeout_s,
            tags=ctx.tags,
        )
        queue_env_key = f"SKAAL_JOB_{ctx.slug_key}_URL"

        # Build the scaffold with the queue URL injected — the base class
        # `_build_scaffold` accepts an `extra_env` kwarg for this purpose.
        scaffold = self._build_scaffold(ctx, extra_env={queue_env_key: queue.url})

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


__all__ = ["SqsWorkerSynth"]
