"""Cloud Scheduler + Cloud Run synth — scheduled `SCHEDULE` resources.

Emits one `gcp.cloudscheduler.Job` that POSTs to a Cloud Run service URL
at the scheduled cadence. The per-resource `Cron` / `Every` trigger from
`ResourceOverrides.trigger` is honoured first; the fallback applies only
when no trigger has been declared.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pulumi
import pulumi_gcp as gcp

from skaal.backends.tokens import CloudSchedulerCloudRun
from skaal.deploy._protocol import SynthContext, SynthSpec, WherePreference, WhereSpec
from skaal.deploy.gcp._cloud_run import CloudRunScaffold, CloudRunSynth, PreScaffold
from skaal.deploy.gcp._config import GcpConfig
from skaal.deploy.gcp._where import (
    GCP_CLOUDRUN_SERVICE,
    GCP_CLOUDSCHEDULER_JOB,
    WHERE_FALLBACK,
    WHERE_PRIMARY,
    cloud_run_console_url,
    cloud_scheduler_console_url,
)
from skaal.inference.model import ResourceKind
from skaal.schedule import Cron, Every


class CloudSchedulerSynth(CloudRunSynth):
    """Cloud Scheduler firing a Cloud Run endpoint."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(CloudSchedulerCloudRun,),
        description="Cloud Scheduler firing a Cloud Run endpoint.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.SCHEDULE,
                    provider_type=GCP_CLOUDSCHEDULER_JOB,
                    priority=WHERE_PRIMARY,
                ),
                WherePreference(
                    kind=ResourceKind.SCHEDULE,
                    provider_type=GCP_CLOUDRUN_SERVICE,
                    priority=WHERE_FALLBACK,
                ),
            ),
            console_url_resolvers={
                GCP_CLOUDSCHEDULER_JOB: cloud_scheduler_console_url,
                GCP_CLOUDRUN_SERVICE: cloud_run_console_url,
            },
        ),
    )

    def _event_source(
        self,
        ctx: SynthContext[GcpConfig],
        scaffold: CloudRunScaffold,
        pre: PreScaffold,
    ) -> tuple[Any, ...]:
        cfg = ctx.config.cloud_scheduler
        overrides = ctx.resource.inferred.overrides
        schedule = self._cron_expression(overrides.trigger, fallback=cfg.fallback_schedule)
        target_uri = pulumi.Output.concat(
            scaffold.service.uri, f"/_skaal/schedule/{ctx.resource_slug}"
        )
        http_target_kwargs: dict[str, Any] = {
            "uri": target_uri,
            "http_method": cfg.http_method,
        }
        if scaffold.service_account is not None:
            http_target_kwargs["oidc_token"] = gcp.cloudscheduler.JobHttpTargetOidcTokenArgs(
                service_account_email=scaffold.service_account.email,
            )
        job = gcp.cloudscheduler.Job(
            f"{ctx.pulumi_name}-job",
            schedule=schedule,
            time_zone=cfg.time_zone,
            http_target=gcp.cloudscheduler.JobHttpTargetArgs(**http_target_kwargs),
        )
        return (job,)

    @staticmethod
    def _cron_expression(trigger: Cron | Every | None, *, fallback: str) -> str:
        if isinstance(trigger, Cron):
            return trigger.expression
        if isinstance(trigger, Every):
            return trigger.as_cron_expression()
        return fallback


__all__ = ["CloudSchedulerSynth"]
