"""RDS Postgres synth — `aws.rds.Instance` for `RELATIONAL` resources.

Configuration tunables live in `AwsConfig.postgres`; override via
``[env.<name>.backends.aws.options.postgres]`` in `skaal.toml`.

RDS manages the master password through Secrets Manager via
``manage_master_user_password``, which avoids embedding any
random-number generator dependency into the deploy program.
"""

from __future__ import annotations

import pulumi_aws as aws

from skaal.deploy._protocol import SynthContext, SynthResult, SynthSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.inference.model import ResourceKind

SPEC = SynthSpec(
    backends=("postgres",),
    kinds=frozenset({ResourceKind.RELATIONAL}),
    description="RDS Postgres instance with managed master credentials.",
)


def synthesize(ctx: SynthContext[AwsConfig]) -> SynthResult:
    """Create one RDS Postgres instance for a `RELATIONAL` bound resource."""
    cfg = ctx.config.postgres
    instance = aws.rds.Instance(
        ctx.pulumi_name,
        allocated_storage=cfg.allocated_storage_gb,
        engine="postgres",
        engine_version=cfg.engine_version,
        instance_class=cfg.instance_class,
        db_name=cfg.db_name,
        username=cfg.username,
        manage_master_user_password=cfg.manage_master_user_password,
        skip_final_snapshot=cfg.skip_final_snapshot,
        publicly_accessible=cfg.publicly_accessible,
        tags=ctx.tags,
    )
    return SynthResult(
        resource_id=ctx.resource_id,
        primary=instance,
        env_vars={
            f"{cfg.env_var_prefix}{ctx.slug_key}_HOST": instance.address,
            f"{cfg.env_var_prefix}{ctx.slug_key}_SECRET_ARN": (
                instance.master_user_secrets[0].secret_arn
            ),
        },
    )


__all__ = ["SPEC", "synthesize"]
