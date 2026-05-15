"""ElastiCache Redis synth — `aws.elasticache.ReplicationGroup`.

Used for both `STORE` resources bound to the `redis` backend and
`CHANNEL` resources bound to `redis-channel`. Phase 4 emits a single-node
replication group on `cache.t3.micro` with no automatic failover; multi-AZ
hardening lands in a follow-up driven by `ResourceOverrides.options`.

The advertised env var (``SKAAL_REDIS_<slug>_URL``) is a ``rediss://``
connection string the Lambda bootstrap consumes.
"""

from __future__ import annotations

import pulumi
import pulumi_aws as aws

from skaal.deploy.aws._context import SynthContext, SynthResult


def synthesize(ctx: SynthContext) -> SynthResult:
    """Create one ElastiCache Redis cluster for a `STORE` or `CHANNEL` resource."""
    rg = aws.elasticache.ReplicationGroup(
        ctx.pulumi_name,
        description=f"Skaal {ctx.resource_id}",
        node_type="cache.t3.micro",
        num_cache_clusters=1,
        engine="redis",
        engine_version="7.1",
        port=6379,
        automatic_failover_enabled=False,
        transit_encryption_enabled=True,
        at_rest_encryption_enabled=True,
        tags=ctx.tags,
    )
    url = pulumi.Output.concat(
        "rediss://", rg.primary_endpoint_address, ":6379"
    )
    env_key = f"SKAAL_REDIS_{ctx.resource_slug.replace('-', '_').upper()}_URL"
    return SynthResult(
        resource_id=ctx.resource_id,
        primary=rg,
        env_vars={env_key: url},
    )


__all__ = ["synthesize"]
