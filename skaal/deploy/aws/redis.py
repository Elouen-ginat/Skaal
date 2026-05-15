"""ElastiCache Redis synth class — `aws.elasticache.ReplicationGroup`.

Used for both `STORE` resources bound to `redis` and `CHANNEL` resources
bound to `redis-channel`. Configuration tunables live in
`AwsConfig.redis`; override via
``[env.<name>.backends.aws.options.redis]`` in `skaal.toml`.
"""

from __future__ import annotations

from typing import ClassVar

import pulumi
import pulumi_aws as aws

from skaal.deploy._protocol import SynthContext, SynthModule, SynthResult, SynthSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.inference.model import ResourceKind


class RedisSynth(SynthModule[AwsConfig]):
    """ElastiCache Redis cluster (single-node replication group, Phase 4 default)."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        backends=("redis", "redis-channel"),
        kinds=frozenset({ResourceKind.STORE, ResourceKind.CHANNEL}),
        description="ElastiCache Redis replication group (store + channel forms).",
    )

    def synthesize(self, ctx: SynthContext[AwsConfig]) -> SynthResult:
        cfg = ctx.config.redis
        rg = aws.elasticache.ReplicationGroup(
            ctx.pulumi_name,
            description=f"Skaal {ctx.resource_id}",
            node_type=cfg.node_type,
            num_cache_clusters=cfg.num_cache_clusters,
            engine="redis",
            engine_version=cfg.engine_version,
            port=cfg.port,
            automatic_failover_enabled=cfg.automatic_failover,
            transit_encryption_enabled=cfg.transit_encryption,
            at_rest_encryption_enabled=cfg.at_rest_encryption,
            tags=ctx.tags,
        )
        scheme = "rediss" if cfg.transit_encryption else "redis"
        url = pulumi.Output.concat(
            f"{scheme}://", rg.primary_endpoint_address, f":{cfg.port}"
        )
        env_key = f"{cfg.env_var_prefix}{ctx.slug_key}{cfg.env_var_suffix}"
        return SynthResult(
            resource_id=ctx.resource_id,
            primary=rg,
            env_vars={env_key: url},
        )


__all__ = ["RedisSynth"]
