"""Pub/Sub synth — one `gcp.pubsub.Topic` per `CHANNEL` resource.

Configuration tunables live in `GcpConfig.pubsub`; override via
``[env.<name>.backends.gcp.options.pubsub]`` in `skaal.toml`.
"""

from __future__ import annotations

from typing import ClassVar

import pulumi_gcp as gcp

from skaal.backends.tokens import Pubsub
from skaal.deploy._protocol import (
    SynthContext,
    SynthModule,
    SynthResult,
    SynthSpec,
    WherePreference,
    WhereSpec,
)
from skaal.deploy.gcp._config import GcpConfig
from skaal.deploy.gcp._where import GCP_PUBSUB_TOPIC, WHERE_PRIMARY, pubsub_console_url
from skaal.inference.model import ResourceKind


class PubsubChannelSynth(SynthModule[GcpConfig]):
    """`gcp.pubsub.Topic` for `Channel[T, Pubsub]` resources."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(Pubsub,),
        description="Pub/Sub topic for pub/sub channels.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.CHANNEL,
                    provider_type=GCP_PUBSUB_TOPIC,
                    priority=WHERE_PRIMARY,
                ),
            ),
            console_url_resolvers={GCP_PUBSUB_TOPIC: pubsub_console_url},
        ),
    )

    def synthesize(self, ctx: SynthContext[GcpConfig]) -> SynthResult:
        cfg = ctx.config.pubsub
        topic = gcp.pubsub.Topic(
            ctx.pulumi_name,
            message_retention_duration=cfg.message_retention_duration,
            labels=ctx.tags,
        )
        env_key = f"{cfg.env_var_prefix}{ctx.slug_key}{cfg.env_var_suffix}"
        return SynthResult(
            resource_id=ctx.resource_id,
            primary=topic,
            env_vars={env_key: topic.name},
        )


__all__ = ["PubsubChannelSynth"]
