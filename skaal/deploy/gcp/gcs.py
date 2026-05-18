"""GCS synth — one `gcp.storage.Bucket` per `BLOB` resource.

Configuration tunables live in `GcpConfig.gcs`; override via
``[env.<name>.backends.gcp.options.gcs]`` in `skaal.toml`.
"""

from __future__ import annotations

from typing import ClassVar

import pulumi_gcp as gcp

from skaal.backends._tokens import Gcs
from skaal.deploy._protocol import (
    SynthContext,
    SynthModule,
    SynthResult,
    SynthSpec,
    WherePreference,
    WhereSpec,
)
from skaal.deploy.gcp._config import GcpConfig
from skaal.deploy.gcp._where import GCP_STORAGE_BUCKET, WHERE_PRIMARY, gcs_console_url
from skaal.inference.model import ResourceKind


class GcsSynth(SynthModule[GcpConfig]):
    """`gcp.storage.Bucket` for `BLOB` resources."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(Gcs,),
        description="GCS bucket for blob storage.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.BLOB,
                    provider_type=GCP_STORAGE_BUCKET,
                    priority=WHERE_PRIMARY,
                ),
            ),
            console_url_resolvers={GCP_STORAGE_BUCKET: gcs_console_url},
        ),
    )

    def synthesize(self, ctx: SynthContext[GcpConfig]) -> SynthResult:
        cfg = ctx.config.gcs
        bucket = gcp.storage.Bucket(
            ctx.pulumi_name,
            location=cfg.location,
            storage_class=cfg.storage_class,
            uniform_bucket_level_access=cfg.uniform_bucket_level_access,
            labels=ctx.tags,
        )
        env_key = f"{cfg.env_var_prefix}{ctx.slug_key}"
        return SynthResult(
            resource_id=ctx.resource_id,
            primary=bucket,
            env_vars={env_key: bucket.name},
        )


__all__ = ["GcsSynth"]
