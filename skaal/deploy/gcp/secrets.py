"""Secret Manager synth — one `gcp.secretmanager.Secret` per `SECRET`.

Configuration tunables live in `GcpConfig.secrets`; override via
``[env.<name>.backends.gcp.options.secrets]`` in `skaal.toml`.
"""

from __future__ import annotations

from typing import ClassVar

import pulumi_gcp as gcp

from skaal.backends._tokens import GcpSecretManager
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
    GCP_SECRETMANAGER_SECRET,
    WHERE_PRIMARY,
    secret_console_url,
)
from skaal.inference.model import ResourceKind


class SecretManagerSynth(SynthModule[GcpConfig]):
    """`gcp.secretmanager.Secret` containers (values supplied out-of-band)."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(GcpSecretManager,),
        description="Secret Manager secret container (value supplied out-of-band).",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.SECRET,
                    provider_type=GCP_SECRETMANAGER_SECRET,
                    priority=WHERE_PRIMARY,
                ),
            ),
            console_url_resolvers={GCP_SECRETMANAGER_SECRET: secret_console_url},
        ),
    )

    def synthesize(self, ctx: SynthContext[GcpConfig]) -> SynthResult:
        cfg = ctx.config.secrets
        replication: gcp.secretmanager.SecretReplicationArgs
        if cfg.replication == "user_managed" and cfg.user_managed_locations:
            replication = gcp.secretmanager.SecretReplicationArgs(
                user_managed=gcp.secretmanager.SecretReplicationUserManagedArgs(
                    replicas=[
                        gcp.secretmanager.SecretReplicationUserManagedReplicaArgs(location=loc)
                        for loc in cfg.user_managed_locations
                    ]
                ),
            )
        else:
            replication = gcp.secretmanager.SecretReplicationArgs(auto={})
        secret = gcp.secretmanager.Secret(
            ctx.pulumi_name,
            secret_id=ctx.resource_slug,
            replication=replication,
            labels=ctx.tags,
        )
        env_key = f"{cfg.env_var_prefix}{ctx.slug_key}{cfg.env_var_suffix}"
        return SynthResult(
            resource_id=ctx.resource_id,
            primary=secret,
            env_vars={env_key: secret.secret_id},
        )


__all__ = ["SecretManagerSynth"]
