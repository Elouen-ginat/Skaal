"""EventBridge + Lambda synth class — scheduled `SCHEDULE` resources.

Configuration tunables live in `AwsConfig.eventbridge` (fallback
schedule expression). The per-resource `Cron` / `Every` trigger from
`ResourceOverrides.trigger` is honoured first; the fallback applies only
when no trigger has been declared.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pulumi_aws as aws

from skaal.backends.tokens import EventBridgeLambda
from skaal.deploy._protocol import SynthContext, SynthSpec, WherePreference, WhereSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._lambda import LambdaScaffold, LambdaSynth, PreScaffold
from skaal.deploy.aws._where import (
    AWS_EVENTBRIDGE_RULE,
    AWS_LAMBDA_FUNCTION,
    WHERE_FALLBACK,
    WHERE_PRIMARY,
    eventbridge_console_url,
    lambda_console_url,
)
from skaal.inference.model import ResourceKind
from skaal.schedule import Cron, Every


class EventBridgeLambdaSynth(LambdaSynth):
    """EventBridge rule firing a scheduled Lambda."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(EventBridgeLambda,),
        description="EventBridge rule firing a scheduled Lambda.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.SCHEDULE,
                    provider_type=AWS_EVENTBRIDGE_RULE,
                    priority=WHERE_PRIMARY,
                ),
                WherePreference(
                    kind=ResourceKind.SCHEDULE,
                    provider_type=AWS_LAMBDA_FUNCTION,
                    priority=WHERE_FALLBACK,
                ),
            ),
            console_url_resolvers={
                AWS_EVENTBRIDGE_RULE: eventbridge_console_url,
                AWS_LAMBDA_FUNCTION: lambda_console_url,
            },
        ),
    )

    def _event_source(
        self,
        ctx: SynthContext[AwsConfig],
        scaffold: LambdaScaffold,
        pre: PreScaffold,
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
            return trigger.as_aws_expression()
        if isinstance(trigger, Every):
            return trigger.as_rate_expression()
        return fallback


__all__ = ["EventBridgeLambdaSynth"]
