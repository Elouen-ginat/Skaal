"""Cloud Tasks + Cloud Run worker synth — `JOB` resources.

Emits one `gcp.cloudtasks.Queue` plus the Cloud Run worker service the
queue dispatches HTTP POSTs to. The queue is built in `_pre_scaffold` so
its name can be injected into the worker's env vars before the service is
constructed. The same queue name is re-exported via `_env_vars` so
downstream FUNCTION resources that want to enqueue tasks pick it up
through the standard peer-env-var mechanism.

Configuration tunables live in `GcpConfig.cloud_tasks`.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pulumi
import pulumi_gcp as gcp

from skaal.backends.tokens import CloudTasksCloudRun
from skaal.deploy._protocol import SynthContext, SynthSpec, WherePreference, WhereSpec
from skaal.deploy.gcp._cloud_run import CloudRunScaffold, CloudRunSynth, PreScaffold
from skaal.deploy.gcp._config import GcpConfig
from skaal.deploy.gcp._where import (
    GCP_CLOUDRUN_SERVICE,
    GCP_CLOUDTASKS_QUEUE,
    WHERE_FALLBACK,
    WHERE_PRIMARY,
    cloud_run_console_url,
    cloud_tasks_console_url,
)
from skaal.inference.model import ResourceKind


class CloudTasksWorkerSynth(CloudRunSynth):
    """Cloud Tasks queue dispatching HTTP POSTs to a Cloud Run worker."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(CloudTasksCloudRun,),
        description="Cloud Tasks queue + Cloud Run worker service.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.JOB,
                    provider_type=GCP_CLOUDTASKS_QUEUE,
                    priority=WHERE_PRIMARY,
                ),
                WherePreference(
                    kind=ResourceKind.JOB,
                    provider_type=GCP_CLOUDRUN_SERVICE,
                    priority=WHERE_FALLBACK,
                ),
            ),
            console_url_resolvers={
                GCP_CLOUDTASKS_QUEUE: cloud_tasks_console_url,
                GCP_CLOUDRUN_SERVICE: cloud_run_console_url,
            },
        ),
    )

    def _timeout_s(self, ctx: SynthContext[GcpConfig]) -> int:
        overrides = ctx.resource.inferred.overrides
        if overrides.timeout_s:
            return int(overrides.timeout_s)
        return ctx.config.cloud_run_job_defaults.timeout_s

    def _memory(self, ctx: SynthContext[GcpConfig]) -> str:
        overrides = ctx.resource.inferred.overrides
        if overrides.memory_mb:
            return f"{overrides.memory_mb}Mi"
        return ctx.config.cloud_run_job_defaults.memory

    def _pre_scaffold(self, ctx: SynthContext[GcpConfig]) -> PreScaffold:
        cfg = ctx.config.cloud_tasks
        location = ctx.env.region or cfg.location
        queue = gcp.cloudtasks.Queue(
            f"{ctx.pulumi_name}-queue",
            location=location,
            rate_limits=gcp.cloudtasks.QueueRateLimitsArgs(
                max_dispatches_per_second=cfg.max_dispatches_per_second,
                max_concurrent_dispatches=cfg.max_concurrent_dispatches,
            ),
            retry_config=gcp.cloudtasks.QueueRetryConfigArgs(max_attempts=cfg.max_attempts),
        )
        queue_env_key = f"{cfg.env_var_prefix}{ctx.slug_key}{cfg.env_var_queue_suffix}"
        return PreScaffold(
            resources=(queue,),
            env_vars={queue_env_key: queue.name},
            payload=queue,
        )

    def _event_source(
        self,
        ctx: SynthContext[GcpConfig],
        scaffold: CloudRunScaffold,
        pre: PreScaffold,
    ) -> tuple[Any, ...]:
        if scaffold.service_account is None:
            return ()
        # Allow the Cloud Tasks service agent to invoke the worker.
        invoker_binding = gcp.cloudrunv2.ServiceIamMember(
            f"{ctx.pulumi_name}-invoker",
            location=scaffold.service.location,
            name=scaffold.service.name,
            role="roles/run.invoker",
            member=pulumi.Output.concat("serviceAccount:", scaffold.service_account.email),
        )
        return (invoker_binding,)


__all__ = ["CloudTasksWorkerSynth"]
