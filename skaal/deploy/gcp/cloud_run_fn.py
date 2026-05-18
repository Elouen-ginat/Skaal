"""Plain Cloud Run synth — `gcp.cloudrunv2.Service` for `FUNCTION` resources.

Configuration tunables live in `GcpConfig.cloud_run_defaults`; override via
``[env.<name>.backends.gcp.options.cloud_run_defaults]`` in `skaal.toml`.
Per-resource overrides (``ResourceOverrides.timeout_s`` / ``.memory_mb``)
take precedence over env-level defaults — handled in
`CloudRunSynth._timeout_s` / `_memory` on the base class.
"""

from __future__ import annotations

from typing import ClassVar

from skaal.backends._tokens import CloudRun
from skaal.deploy._protocol import SynthContext, SynthSpec, WherePreference, WhereSpec
from skaal.deploy.gcp._cloud_run import CloudRunSynth
from skaal.deploy.gcp._config import GcpConfig
from skaal.deploy.gcp._where import GCP_CLOUDRUN_SERVICE, WHERE_PRIMARY, cloud_run_console_url
from skaal.inference.model import ResourceKind


class CloudRunFunctionSynth(CloudRunSynth):
    """Cloud Run service for FUNCTION and ASGI_SERVICE resources.

    The `CloudRun` token covers both kinds, so this single synth class
    handles both — the only difference is which `GcpConfig` section
    supplies the timeout / memory defaults. Overrides on the resource
    (`ResourceOverrides.timeout_s` / `.memory_mb`) win over either.
    """

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(CloudRun,),
        description="Cloud Run service for function and ASGI workloads.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.FUNCTION,
                    provider_type=GCP_CLOUDRUN_SERVICE,
                    priority=WHERE_PRIMARY,
                ),
                WherePreference(
                    kind=ResourceKind.ASGI_SERVICE,
                    provider_type=GCP_CLOUDRUN_SERVICE,
                    priority=WHERE_PRIMARY,
                ),
            ),
            console_url_resolvers={GCP_CLOUDRUN_SERVICE: cloud_run_console_url},
        ),
    )

    def _timeout_s(self, ctx: SynthContext[GcpConfig]) -> int:
        overrides = ctx.resource.inferred.overrides
        if overrides.timeout_s:
            return int(overrides.timeout_s)
        if ctx.resource.inferred.kind is ResourceKind.ASGI_SERVICE:
            return ctx.config.cloud_run_asgi_defaults.timeout_s
        return ctx.config.cloud_run_defaults.timeout_s

    def _memory(self, ctx: SynthContext[GcpConfig]) -> str:
        overrides = ctx.resource.inferred.overrides
        if overrides.memory_mb:
            return f"{overrides.memory_mb}Mi"
        if ctx.resource.inferred.kind is ResourceKind.ASGI_SERVICE:
            return ctx.config.cloud_run_asgi_defaults.memory
        return ctx.config.cloud_run_defaults.memory

    def _max_instances(self, ctx: SynthContext[GcpConfig]) -> int:
        if ctx.resource.inferred.kind is ResourceKind.ASGI_SERVICE:
            return ctx.config.cloud_run_asgi_defaults.max_instances
        return ctx.config.cloud_run_defaults.max_instances


__all__ = ["CloudRunFunctionSynth"]
