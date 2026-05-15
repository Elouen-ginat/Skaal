"""RDS Postgres synth — `aws.rds.Instance` for `RELATIONAL` resources.

Phase 4 emits a minimal single-AZ `db.t3.micro` instance. RDS manages the
master password through Secrets Manager via ``manage_master_user_password``,
which avoids embedding any random-number generator dependency into the
deploy program and matches AWS's recommended pattern for new clusters.

The DB lives in AWS's default VPC subnets; serious deployments will
override this through `ResourceOverrides.options` in a follow-up. The
instance is publicly inaccessible by default.

The advertised env vars (``SKAAL_DB_<slug>_HOST`` and
``SKAAL_DB_<slug>_SECRET_ARN``) point the Lambda bootstrap at the host
and the secret carrying the credentials.
"""

from __future__ import annotations

import pulumi_aws as aws

from skaal.deploy.aws._context import SynthContext, SynthResult


def synthesize(ctx: SynthContext) -> SynthResult:
    """Create one RDS Postgres instance for a `RELATIONAL` bound resource."""
    instance = aws.rds.Instance(
        ctx.pulumi_name,
        allocated_storage=20,
        engine="postgres",
        engine_version="16",
        instance_class="db.t3.micro",
        db_name="skaal",
        username="skaal",
        manage_master_user_password=True,
        skip_final_snapshot=True,
        publicly_accessible=False,
        tags=ctx.tags,
    )
    slug_key = ctx.resource_slug.replace("-", "_").upper()
    return SynthResult(
        resource_id=ctx.resource_id,
        primary=instance,
        env_vars={
            f"SKAAL_DB_{slug_key}_HOST": instance.address,
            f"SKAAL_DB_{slug_key}_SECRET_ARN": instance.master_user_secrets[0].secret_arn,
        },
    )


__all__ = ["synthesize"]
