"""EventBridge + Lambda synth — scheduled `SCHEDULE` resources.

Builds the standard Lambda scaffold (ECR / image / IAM / log group / fn)
and wires an `aws.cloudwatch.EventRule` plus a `Target` that invokes the
Lambda on a schedule. Cron / interval expressions come from
`ResourceOverrides.trigger` (Phase 4 §4.9 reshape); fall back to a
once-a-day rate expression when no trigger is set.
"""

from __future__ import annotations

import pulumi_aws as aws

from skaal.deploy.aws._context import SynthContext, SynthResult
from skaal.deploy.aws._lambda_common import build_lambda
from skaal.schedule import Cron, Every


def synthesize(ctx: SynthContext) -> SynthResult:
    """Create a scheduled Lambda for a `SCHEDULE` bound resource."""
    overrides = ctx.resource.inferred.overrides
    scaffold = build_lambda(
        ctx,
        timeout=int(overrides.timeout_s) if overrides.timeout_s else 30,
        memory_mb=overrides.memory_mb or 512,
    )

    schedule_expression = _schedule_expression(overrides.trigger)
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


def _schedule_expression(trigger: Cron | Every | None) -> str:
    """Translate a `Cron` / `Every` trigger to an EventBridge expression."""
    if isinstance(trigger, Cron):
        return f"cron({trigger.expression})"
    if isinstance(trigger, Every):
        return trigger.as_rate_expression()
    return "rate(1 day)"


__all__ = ["synthesize"]
