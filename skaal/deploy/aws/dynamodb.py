"""DynamoDB synth module — emit one `aws.dynamodb.Table` per `STORE` resource.

Phase 4 ships a minimal table: a single string `pk` partition key, pay-per-request
billing, and the canonical Skaal tag set. Secondary indexes from
`InferredResource.indexes` and TTL configuration land in Phase 6 when the
bytecode walker emits the necessary edges.

The advertised env var (``SKAAL_TABLE_<slug>``) is consumed by the
compute-side Lambda synth modules so the running container can read the
table name without hard-coding it at build time.
"""

from __future__ import annotations

import pulumi_aws as aws

from skaal.deploy.aws._context import SynthContext, SynthResult


def synthesize(ctx: SynthContext) -> SynthResult:
    """Create one DynamoDB table for a `STORE` bound resource."""
    table = aws.dynamodb.Table(
        ctx.pulumi_name,
        billing_mode="PAY_PER_REQUEST",
        hash_key="pk",
        attributes=[aws.dynamodb.TableAttributeArgs(name="pk", type="S")],
        tags=ctx.tags,
    )
    env_key = f"SKAAL_TABLE_{ctx.resource_slug.replace('-', '_').upper()}"
    return SynthResult(
        resource_id=ctx.resource_id,
        primary=table,
        env_vars={env_key: table.name},
    )


__all__ = ["synthesize"]
