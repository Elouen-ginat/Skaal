"""DynamoDB synth — emit one `aws.dynamodb.Table` per `STORE` resource.

Configuration tunables live in `AwsConfig.dynamodb`; override via
``[env.<name>.backends.aws.options.dynamodb]`` in `skaal.toml`.
"""

from __future__ import annotations

import pulumi_aws as aws

from skaal.deploy._protocol import SynthContext, SynthResult, SynthSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.inference.model import ResourceKind

SPEC = SynthSpec(
    backends=("dynamodb",),
    kinds=frozenset({ResourceKind.STORE}),
    description="DynamoDB table for KV stores.",
)


def synthesize(ctx: SynthContext[AwsConfig]) -> SynthResult:
    """Create one DynamoDB table for a `STORE` bound resource."""
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


__all__ = ["SPEC", "synthesize"]
