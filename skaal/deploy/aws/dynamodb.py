"""DynamoDB synth class — emit one `aws.dynamodb.Table` per `STORE` resource.

Configuration tunables live in `AwsConfig.dynamodb`; override via
``[env.<name>.backends.aws.options.dynamodb]`` in `skaal.toml`.
"""

from __future__ import annotations

from typing import ClassVar

import pulumi_aws as aws

from skaal.backends._tokens import DynamoDB
from skaal.deploy._protocol import (
    SynthContext,
    SynthModule,
    SynthResult,
    SynthSpec,
    WherePreference,
    WhereSpec,
)
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._where import AWS_DYNAMODB_TABLE, WHERE_PRIMARY, dynamodb_console_url
from skaal.inference.model import ResourceKind


class DynamoDBSynth(SynthModule[AwsConfig]):
    """`aws.dynamodb.Table` for KV `STORE` resources."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(DynamoDB,),
        description="DynamoDB table for KV stores.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.STORE,
                    provider_type=AWS_DYNAMODB_TABLE,
                    priority=WHERE_PRIMARY,
                ),
            ),
            console_url_resolvers={AWS_DYNAMODB_TABLE: dynamodb_console_url},
        ),
    )

    def synthesize(self, ctx: SynthContext[AwsConfig]) -> SynthResult:
        cfg = ctx.config.dynamodb
        table = aws.dynamodb.Table(
            ctx.pulumi_name,
            billing_mode=cfg.billing_mode,
            hash_key=cfg.partition_key_name,
            attributes=[
                aws.dynamodb.TableAttributeArgs(
                    name=cfg.partition_key_name, type=cfg.partition_key_type
                )
            ],
            tags=ctx.tags,
        )
        env_key = f"{cfg.env_var_prefix}{ctx.slug_key}"
        return SynthResult(
            resource_id=ctx.resource_id,
            primary=table,
            env_vars={env_key: table.name},
        )


__all__ = ["DynamoDBSynth"]
