"""SQS channel synth class — `aws.sqs.Queue` per `CHANNEL` bound to `sqs`.

Configuration tunables live in `AwsConfig.sqs`; override via
``[env.<name>.backends.aws.options.sqs]`` in `skaal.toml`.
"""

from __future__ import annotations

from typing import ClassVar

import pulumi_aws as aws

from skaal.deploy._protocol import (
    SynthContext,
    SynthModule,
    SynthResult,
    SynthSpec,
    WherePreference,
    WhereSpec,
)
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._where import AWS_SQS_QUEUE, WHERE_PRIMARY, sqs_console_url
from skaal.inference.model import ResourceKind


class SqsChannelSynth(SynthModule[AwsConfig]):
    """`aws.sqs.Queue` for pub/sub channels (`Channel[T, Sqs]`)."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        backends=("sqs",),
        kinds=frozenset({ResourceKind.CHANNEL}),
        description="SQS standard queue for pub/sub channels.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.CHANNEL,
                    provider_type=AWS_SQS_QUEUE,
                    priority=WHERE_PRIMARY,
                ),
            ),
            console_url_resolvers={AWS_SQS_QUEUE: sqs_console_url},
        ),
    )

    def synthesize(self, ctx: SynthContext[AwsConfig]) -> SynthResult:
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


__all__ = ["SqsChannelSynth"]
