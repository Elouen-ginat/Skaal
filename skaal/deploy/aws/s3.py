"""S3 synth class — emit one `aws.s3.BucketV2` per `BLOB` resource.

Configuration tunables live in `AwsConfig.s3`; override via
``[env.<name>.backends.aws.options.s3]`` in `skaal.toml`.
"""

from __future__ import annotations

from typing import ClassVar

import pulumi_aws as aws

from skaal.backends._tokens import S3
from skaal.deploy._protocol import (
    SynthContext,
    SynthModule,
    SynthResult,
    SynthSpec,
    WherePreference,
    WhereSpec,
)
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._where import AWS_S3_BUCKET, WHERE_PRIMARY, s3_console_url
from skaal.inference.model import ResourceKind


class S3Synth(SynthModule[AwsConfig]):
    """`aws.s3.BucketV2` for `BLOB` resources, plus an SSE configuration."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(S3,),
        description="S3 bucket with server-side encryption.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.BLOB,
                    provider_type=AWS_S3_BUCKET,
                    priority=WHERE_PRIMARY,
                ),
            ),
            console_url_resolvers={AWS_S3_BUCKET: s3_console_url},
        ),
    )

    def synthesize(self, ctx: SynthContext[AwsConfig]) -> SynthResult:
        cfg = ctx.config.s3
        bucket = aws.s3.BucketV2(ctx.pulumi_name, tags=ctx.tags)
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


__all__ = ["S3Synth"]
