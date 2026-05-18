"""Firestore synth — one `gcp.firestore.Database` per `STORE` resource.

Configuration tunables live in `GcpConfig.firestore`; override via
``[env.<name>.backends.gcp.options.firestore]`` in `skaal.toml`.
"""

from __future__ import annotations

from typing import ClassVar

import pulumi_gcp as gcp

from skaal.backends.tokens import Firestore
from skaal.deploy._protocol import (
    SynthContext,
    SynthModule,
    SynthResult,
    SynthSpec,
    WherePreference,
    WhereSpec,
)
from skaal.deploy.gcp._config import GcpConfig
from skaal.deploy.gcp._where import (
    GCP_FIRESTORE_DATABASE,
    WHERE_PRIMARY,
    firestore_console_url,
)
from skaal.inference.model import ResourceKind


class FirestoreSynth(SynthModule[GcpConfig]):
    """`gcp.firestore.Database` for KV `STORE` resources."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(Firestore,),
        description="Firestore database for KV stores.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.STORE,
                    provider_type=GCP_FIRESTORE_DATABASE,
                    priority=WHERE_PRIMARY,
                ),
            ),
            console_url_resolvers={GCP_FIRESTORE_DATABASE: firestore_console_url},
        ),
    )

    def synthesize(self, ctx: SynthContext[GcpConfig]) -> SynthResult:
        cfg = ctx.config.firestore
        database = gcp.firestore.Database(
            ctx.pulumi_name,
            name=ctx.resource_slug,
            location_id=cfg.location_id,
            type=cfg.type_,
        )
        env_key = f"{cfg.env_var_prefix}{ctx.slug_key}"
        return SynthResult(
            resource_id=ctx.resource_id,
            primary=database,
            env_vars={env_key: database.name},
        )


__all__ = ["FirestoreSynth"]
