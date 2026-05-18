"""GCP deploy target (ADR 042).

This package contributes one `DeployTarget` (`GcpTarget`) to the registry
at import time. Each synth module under this package exports a single
`SynthModule` subclass that declares its `SPEC: ClassVar[SynthSpec]` and
implements `synthesize(ctx)`. `GcpTarget.from_classes(_SYNTHS)` walks the
tuple, instantiates each class, and assembles the dispatch table.

**Adding a new GCP backend**: drop a new module with a `SynthModule`
subclass, then add the class to `_SYNTHS`. Cloud Run-shaped backends
should inherit from `CloudRunSynth` so they reuse the Artifact Registry
+ image + service-account + Cloud Run scaffold; storage backends inherit
directly from `SynthModule[GcpConfig]`.
"""

from __future__ import annotations

from skaal.deploy._protocol import SynthModule
from skaal.deploy._registry import register_target
from skaal.deploy.gcp._config import GcpConfig
from skaal.deploy.gcp._target import GcpTarget


def _load_synths() -> tuple[type[SynthModule[GcpConfig]], ...]:
    """Load GCP synths when optional Pulumi dependencies are available.

    Importing `skaal.deploy.gcp` should stay safe for read-only code paths
    like `skaal where`, which only need target identity and static metadata.
    When the Pulumi SDKs are missing we register an empty target here;
    build/deploy flows will still fail later when they need those extras.
    """
    try:
        from skaal.deploy.gcp.bigquery import BigQuerySynth
        from skaal.deploy.gcp.cloud_run_fn import CloudRunFunctionSynth
        from skaal.deploy.gcp.cloud_scheduler import CloudSchedulerSynth
        from skaal.deploy.gcp.cloud_tasks import CloudTasksWorkerSynth
        from skaal.deploy.gcp.firestore import FirestoreSynth
        from skaal.deploy.gcp.gcs import GcsSynth
        from skaal.deploy.gcp.postgres import CloudSqlPostgresSynth
        from skaal.deploy.gcp.pubsub import PubsubChannelSynth
        from skaal.deploy.gcp.secrets import SecretManagerSynth
    except ModuleNotFoundError as exc:
        if exc.name not in {"pulumi", "pulumi_gcp", "pulumi_docker"}:
            raise
        return ()

    return (
        FirestoreSynth,
        GcsSynth,
        PubsubChannelSynth,
        SecretManagerSynth,
        CloudSqlPostgresSynth,
        BigQuerySynth,
        CloudRunFunctionSynth,
        CloudSchedulerSynth,
        CloudTasksWorkerSynth,
    )


TARGET = GcpTarget.from_classes(_load_synths())
register_target(TARGET)


__all__ = ["TARGET", "GcpConfig", "GcpTarget"]
