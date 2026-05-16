"""SQS + Lambda worker synth class — `JOB` resources.

The queue is built in `_pre_scaffold` so its URL can be injected into
the Lambda's env vars before the function is constructed. The
`_event_source` hook then attaches the IAM policy and the
EventSourceMapping that wires the queue to the Lambda. The same URL is
re-exported via `_env_vars` so downstream FUNCTION resources that want
to enqueue jobs pick it up through the standard peer-env-var mechanism.

Configuration tunables live in `AwsConfig.lambda_defaults` (timeout /
visibility timeout / batch size).
"""

from __future__ import annotations

from typing import Any, ClassVar

import pulumi_aws as aws

from skaal.backends._tokens import SqsLambdaWorker
from skaal.deploy._protocol import SynthContext, SynthSpec, WherePreference, WhereSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._lambda import LambdaScaffold, LambdaSynth, PreScaffold
from skaal.deploy.aws._where import (
    AWS_LAMBDA_FUNCTION,
    AWS_SQS_QUEUE,
    WHERE_FALLBACK,
    WHERE_PRIMARY,
    lambda_console_url,
    sqs_console_url,
)
from skaal.inference.model import ResourceKind


class SqsWorkerSynth(LambdaSynth):
    """SQS queue + Lambda worker (event-source mapping)."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(SqsLambdaWorker,),
        description="SQS queue + Lambda worker (event-source mapping).",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.JOB,
                    provider_type=AWS_SQS_QUEUE,
                    priority=WHERE_PRIMARY,
                ),
                WherePreference(
                    kind=ResourceKind.JOB,
                    provider_type=AWS_LAMBDA_FUNCTION,
                    priority=WHERE_FALLBACK,
                ),
            ),
            console_url_resolvers={
                AWS_SQS_QUEUE: sqs_console_url,
                AWS_LAMBDA_FUNCTION: lambda_console_url,
            },
        ),
    )

    def _timeout_s(self, ctx: SynthContext[AwsConfig]) -> int:
        overrides = ctx.resource.inferred.overrides
        if overrides.timeout_s:
            return int(overrides.timeout_s)
        return ctx.config.lambda_defaults.job_timeout_s

    def _pre_scaffold(self, ctx: SynthContext[AwsConfig]) -> PreScaffold:
        cfg = ctx.config
        queue = aws.sqs.Queue(
            f"{ctx.pulumi_name}-queue",
            visibility_timeout_seconds=cfg.lambda_defaults.job_visibility_timeout_s,
            tags=ctx.tags,
        )
        queue_env_key = f"SKAAL_JOB_{ctx.slug_key}_URL"
        return PreScaffold(
            resources=(queue,),
            env_vars={queue_env_key: queue.url},
            payload=queue,
        )

    def _event_source(
        self,
        ctx: SynthContext[AwsConfig],
        scaffold: LambdaScaffold,
        pre: PreScaffold,
    ) -> tuple[Any, ...]:
        cfg = ctx.config
        queue: aws.sqs.Queue = pre.payload
        extras: list[Any] = []
        if "sqs" in cfg.iam.policies:
            extras.append(
                aws.iam.RolePolicyAttachment(
                    f"{ctx.pulumi_name}-sqs-consume",
                    role=scaffold.role.name,
                    policy_arn=cfg.iam.policies["sqs"],
                )
            )
        extras.append(
            aws.lambda_.EventSourceMapping(
                f"{ctx.pulumi_name}-mapping",
                event_source_arn=queue.arn,
                function_name=scaffold.function.name,
                batch_size=cfg.lambda_defaults.job_batch_size,
            )
        )
        return tuple(extras)


__all__ = ["SqsWorkerSynth"]
