"""EventBridge + Lambda synth class — scheduled `SCHEDULE` resources.

Configuration tunables live in `AwsConfig.eventbridge` (fallback
schedule expression). The per-resource `Cron` / `Every` trigger from
`ResourceOverrides.trigger` is honoured first; the fallback applies only
when no trigger has been declared.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pulumi_aws as aws

from skaal.deploy._protocol import SynthContext, SynthSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._lambda import LambdaScaffold, LambdaSynth
from skaal.inference.model import ResourceKind
from skaal.schedule import Cron, Every


class EventBridgeLambdaSynth(LambdaSynth):
    """EventBridge rule firing a scheduled Lambda."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        backends=("eventbridge-lambda",),
        kinds=frozenset({ResourceKind.SCHEDULE}),
        description="EventBridge rule firing a scheduled Lambda.",
    )

    def _event_source(
        self, ctx: SynthContext[AwsConfig], scaffold: LambdaScaffold
    ) -> tuple[Any, ...]:
        cfg = ctx.config.eventbridge
        overrides = ctx.resource.inferred.overrides
        expression = self._schedule_expression(
            overrides.trigger, fallback=cfg.fallback_schedule_expression
        )
        rule = aws.cloudwatch.EventRule(
            f"{ctx.pulumi_name}-rule",
            schedule_expression=expression,
            tags=ctx.tags,
        )
        target = aws.cloudwatch.EventTarget(
            f"{ctx.pulumi_name}-target",
            rule=rule.name,
            arn=scaffold.function.arn,
        )
        permission = aws.lambda_.Permission(
            f"{ctx.pulumi_name}-perm",
            action="lambda:InvokeFunction",
            function=scaffold.function.name,
            principal="events.amazonaws.com",
            source_arn=rule.arn,
        )
        return (rule, target, permission)

    @staticmethod
    def _schedule_expression(trigger: Cron | Every | None, *, fallback: str) -> str:
        if isinstance(trigger, Cron):
            return f"cron({trigger.expression})"
        if isinstance(trigger, Every):
            return trigger.as_rate_expression()
        return fallback


__all__ = ["EventBridgeLambdaSynth"]
