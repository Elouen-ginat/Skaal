"""EventBridge + Lambda synth — scheduled `SCHEDULE` resources.

Configuration tunables live in `AwsConfig.eventbridge` (fallback
schedule expression). The per-resource `Cron` / `Every` trigger from
`ResourceOverrides.trigger` is honoured first; the fallback applies only
when no trigger has been declared.
"""

from __future__ import annotations

import pulumi_aws as aws

from skaal.deploy._protocol import SynthContext, SynthResult, SynthSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._lambda_common import build_lambda
from skaal.inference.model import ResourceKind
from skaal.schedule import Cron, Every

SPEC = SynthSpec(
    backends=("eventbridge-lambda",),
    kinds=frozenset({ResourceKind.SCHEDULE}),
    description="EventBridge rule firing a scheduled Lambda.",
)


def synthesize(ctx: SynthContext[AwsConfig]) -> SynthResult:
    """Create a scheduled Lambda for a `SCHEDULE` bound resource."""
    cfg = ctx.config
    overrides = ctx.resource.inferred.overrides
    scaffold = build_lambda(
        ctx,
        timeout=int(overrides.timeout_s) if overrides.timeout_s else None,
        memory_mb=overrides.memory_mb,
    )

    schedule_expression = _schedule_expression(
        overrides.trigger, fallback=cfg.eventbridge.fallback_schedule_expression
    )
    rule = aws.cloudwatch.EventRule(
        f"{ctx.pulumi_name}-rule",
        schedule_expression=schedule_expression,
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

    return SynthResult(
        resource_id=ctx.resource_id,
        primary=scaffold.function,
        extras=(*scaffold.as_extras(), rule, target, permission),
    )


def _schedule_expression(trigger: Cron | Every | None, *, fallback: str) -> str:
    """Translate a `Cron` / `Every` trigger to an EventBridge expression."""
    if isinstance(trigger, Cron):
        return f"cron({trigger.expression})"
    if isinstance(trigger, Every):
        return trigger.as_rate_expression()
    return fallback


__all__ = ["SPEC", "synthesize"]
