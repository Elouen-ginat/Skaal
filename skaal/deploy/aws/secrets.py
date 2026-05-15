"""AWS Secrets Manager synth — one `aws.secretsmanager.Secret` per `SECRET` resource.

Phase 4 emits the secret container only. The actual secret *value* lives in
``Environment.backends[<name>].options`` or is supplied out-of-band by the
operator after the first deploy; ADR 028 §6.11 explicitly forbids
embedding secrets in generated Pulumi programs.

The advertised env var (``SKAAL_SECRET_<slug>_ARN``) lets the Lambda
bootstrap layer call `secretsmanager:GetSecretValue` on the correct ARN
at warm-up time.
"""

from __future__ import annotations

import pulumi_aws as aws

from skaal.deploy.aws._context import SynthContext, SynthResult


def synthesize(ctx: SynthContext) -> SynthResult:
    """Create one Secrets Manager container for a `SECRET` bound resource."""
    secret = aws.secretsmanager.Secret(
        ctx.pulumi_name,
        tags=ctx.tags,
    )
    env_key = f"SKAAL_SECRET_{ctx.resource_slug.replace('-', '_').upper()}_ARN"
    return SynthResult(
        resource_id=ctx.resource_id,
        primary=secret,
        env_vars={env_key: secret.arn},
    )


__all__ = ["synthesize"]
