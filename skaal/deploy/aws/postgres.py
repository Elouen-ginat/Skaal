"""RDS Postgres synth class — `aws.rds.Instance` for `RELATIONAL` resources.

Configuration tunables live in `AwsConfig.postgres`; override via
``[env.<name>.backends.aws.options.postgres]`` in `skaal.toml`.
RDS manages the master password through Secrets Manager via
``manage_master_user_password``.
"""

from __future__ import annotations

from typing import ClassVar

import pulumi_aws as aws

from skaal.backends._tokens import Postgres
from skaal.deploy._protocol import (
    SynthContext,
    SynthModule,
    SynthResult,
    SynthSpec,
    WherePreference,
    WhereSpec,
)
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._where import AWS_RDS_INSTANCE, WHERE_PRIMARY, rds_console_url
from skaal.inference.model import ResourceKind


class PostgresSynth(SynthModule[AwsConfig]):
    """RDS Postgres instance with managed master credentials."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(Postgres,),
        description="RDS Postgres instance with managed master credentials.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.RELATIONAL,
                    provider_type=AWS_RDS_INSTANCE,
                    priority=WHERE_PRIMARY,
                ),
            ),
            console_url_resolvers={AWS_RDS_INSTANCE: rds_console_url},
        ),
    )

    def synthesize(self, ctx: SynthContext[AwsConfig]) -> SynthResult:
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


__all__ = ["PostgresSynth"]
