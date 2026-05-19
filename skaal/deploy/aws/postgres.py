"""RDS Postgres synth class — `aws.rds.Instance` for `RELATIONAL` resources.

Configuration tunables live in `AwsConfig.postgres`; override via
``[env.<name>.backends.aws.options.postgres]`` in `skaal.toml`.
By default Skaal writes the generated master credentials into its own
Secrets Manager secret; setting ``manage_master_user_password`` delegates
that secret management back to RDS.
"""

from __future__ import annotations

from typing import ClassVar

import pulumi
import pulumi_aws as aws
import pulumi_random as random

from skaal.backends.tokens import Postgres
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
    """RDS Postgres instance with Secrets Manager-backed credentials."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(Postgres,),
        description="RDS Postgres instance with Secrets Manager-backed credentials.",
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
        extras: list[object] = []

        if cfg.manage_master_user_password:
            secret_arn: pulumi.Input[str] = pulumi.Output.concat(ctx.pulumi_name, "-managed-secret")
            instance = aws.rds.Instance(
                ctx.pulumi_name,
                allocated_storage=cfg.allocated_storage_gb,
                engine="postgres",
                engine_version=cfg.engine_version,
                instance_class=cfg.instance_class,
                db_name=cfg.db_name,
                username=cfg.username,
                manage_master_user_password=True,
                skip_final_snapshot=cfg.skip_final_snapshot,
                publicly_accessible=cfg.publicly_accessible,
                tags=ctx.tags,
            )
        else:
            password_resource = random.RandomPassword(
                f"{ctx.pulumi_name}-password",
                length=32,
                special=False,
            )
            secret = aws.secretsmanager.Secret(f"{ctx.pulumi_name}-secret", tags=ctx.tags)
            secret_version = aws.secretsmanager.SecretVersion(
                f"{ctx.pulumi_name}-secret-version",
                secret_id=secret.id,
                secret_string=pulumi.Output.json_dumps(
                    {
                        "username": cfg.username,
                        "password": password_resource.result,
                        "port": 5432,
                        "dbname": cfg.db_name,
                    }
                ),
            )
            secret_arn = secret.arn
            extras.extend((password_resource, secret, secret_version))
            instance = aws.rds.Instance(
                ctx.pulumi_name,
                allocated_storage=cfg.allocated_storage_gb,
                engine="postgres",
                engine_version=cfg.engine_version,
                instance_class=cfg.instance_class,
                db_name=cfg.db_name,
                username=cfg.username,
                password=password_resource.result,
                skip_final_snapshot=cfg.skip_final_snapshot,
                publicly_accessible=cfg.publicly_accessible,
                tags=ctx.tags,
            )
        if cfg.manage_master_user_password:
            secret_arn = instance.master_user_secrets[0].secret_arn
        return SynthResult(
            resource_id=ctx.resource_id,
            primary=instance,
            extras=tuple(extras),
            env_vars={
                f"{cfg.env_var_prefix}{ctx.slug_key}_HOST": instance.address,
                f"{cfg.env_var_prefix}{ctx.slug_key}_SECRET_ARN": secret_arn,
            },
        )


__all__ = ["PostgresSynth"]
