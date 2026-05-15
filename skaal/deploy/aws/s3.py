"""S3 synth — emit one `aws.s3.BucketV2` per `BLOB` resource.

Configuration tunables live in `AwsConfig.s3`; override via
``[env.<name>.backends.aws.options.s3]`` in `skaal.toml`.
"""

from __future__ import annotations

import pulumi_aws as aws

from skaal.deploy._protocol import SynthContext, SynthResult, SynthSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.inference.model import ResourceKind

SPEC = SynthSpec(
    backends=("s3",),
    kinds=frozenset({ResourceKind.BLOB}),
    description="S3 bucket with server-side encryption.",
)


def synthesize(ctx: SynthContext[AwsConfig]) -> SynthResult:
    """Create one S3 bucket for a `BLOB` bound resource."""
    cfg = ctx.config.s3
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
                        sse_algorithm=cfg.sse_algorithm
                    )
                )
            )
        ],
    )
    env_key = f"{cfg.env_var_prefix}{ctx.slug_key}"
    return SynthResult(
        resource_id=ctx.resource_id,
        primary=bucket,
        extras=(sse,),
        env_vars={env_key: bucket.bucket},
    )


__all__ = ["SPEC", "synthesize"]
