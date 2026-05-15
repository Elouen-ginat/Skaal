"""S3 synth module — emit one `aws.s3.BucketV2` per `BLOB` resource.

The bucket name is left to Pulumi auto-naming so multiple deploys of the
same app stay isolated. Server-side encryption defaults to AES256 (S3's
managed key). Lifecycle rules and bucket policies are intentionally
omitted in Phase 4; the Phase 6 edge walker drives those once it knows
which functions read/write which buckets.
"""

from __future__ import annotations

import pulumi_aws as aws

from skaal.deploy.aws._context import SynthContext, SynthResult


def synthesize(ctx: SynthContext) -> SynthResult:
    """Create one S3 bucket for a `BLOB` bound resource."""
    bucket = aws.s3.BucketV2(
        ctx.pulumi_name,
        tags=ctx.tags,
    )
    sse = aws.s3.BucketServerSideEncryptionConfigurationV2(
        f"{ctx.pulumi_name}-sse",
        bucket=bucket.id,
        rules=[
            aws.s3.BucketServerSideEncryptionConfigurationV2RuleArgs(
                apply_server_side_encryption_by_default=(
                    aws.s3.BucketServerSideEncryptionConfigurationV2RuleApplyServerSideEncryptionByDefaultArgs(
                        sse_algorithm="AES256"
                    )
                )
            )
        ],
    )
    env_key = f"SKAAL_BUCKET_{ctx.resource_slug.replace('-', '_').upper()}"
    return SynthResult(
        resource_id=ctx.resource_id,
        primary=bucket,
        extras=(sse,),
        env_vars={env_key: bucket.bucket},
    )


__all__ = ["synthesize"]
