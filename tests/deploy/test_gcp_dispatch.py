"""Structural tests for the GCP `DeployTarget` (ADR 042)."""

from __future__ import annotations

import pytest

pytest.importorskip("pulumi_gcp")
pytest.importorskip("pulumi_docker")

from skaal.binding.model import Target
from skaal.binding.registry import REGISTRY
from skaal.deploy import DeployTarget, get_target
from skaal.deploy.gcp import TARGET, GcpConfig, GcpTarget


def test_gcp_target_satisfies_deploy_target_protocol() -> None:
    assert isinstance(TARGET, DeployTarget)
    assert isinstance(TARGET, GcpTarget)


def test_gcp_target_registered_in_registry() -> None:
    assert get_target(Target.GCP) is TARGET


def test_gcp_target_covers_every_gcp_backend() -> None:
    gcp_backends = {entry.token_class.name for entry in REGISTRY if Target.GCP in entry.targets}
    # Tokens shared with AWS / local (Postgres, Redis, RedisChannel) only
    # need a synth on the *specific* target that owns them; here we check
    # that every backend tagged for GCP has a GCP synth or is intentionally
    # delegated (Redis / RedisChannel use the same Pulumi shape on every
    # cloud and are deferred to a future polish PR).
    expected_with_gcp_synth = {
        "firestore",
        "gcs",
        "pubsub",
        "postgres",
        "bigquery",
        "gcp-secret-manager",
        "cloud-run",
        "cloud-scheduler-run",
        "cloud-tasks-run",
    }
    missing = expected_with_gcp_synth - TARGET.supported_backends()
    assert not missing, f"GCP backends without a synth module: {sorted(missing)}"
    # Sanity-check the inverse: every supported backend is a registered GCP backend.
    assert TARGET.supported_backends() <= gcp_backends


def test_gcp_target_required_extras_match_sdks() -> None:
    assert TARGET.required_extras() == ("pulumi", "pulumi_gcp", "pulumi_docker")


def test_gcp_target_default_config_is_typed() -> None:
    cfg = TARGET.default_config()
    assert isinstance(cfg, GcpConfig)
    assert cfg.cloud_run_defaults.memory == "512Mi"
    assert cfg.bigquery.location == "US"


def test_gcp_target_config_overlays_env_options() -> None:
    from skaal.binding.model import BackendConfig, Environment

    env = Environment(
        name="prod",
        target=Target.GCP,
        region="us-central1",
        backends={
            "gcp": BackendConfig(
                options={
                    "cloud_run_defaults": {"memory": "1Gi", "timeout_s": 600},
                    "bigquery": {"location": "EU"},
                }
            )
        },
    )
    cfg = TARGET.config_for(env)
    assert isinstance(cfg, GcpConfig)
    assert cfg.cloud_run_defaults.memory == "1Gi"
    assert cfg.cloud_run_defaults.timeout_s == 600
    assert cfg.bigquery.location == "EU"
    # Other fields keep defaults
    assert cfg.firestore.location_id == "nam5"


def test_gcp_target_stack_config_wires_project_and_region() -> None:
    from skaal.binding.model import BackendConfig, Environment

    env = Environment(
        name="prod",
        target=Target.GCP,
        region="us-central1",
        backends={"gcp": BackendConfig(project="acme-prod")},
    )
    config = TARGET.stack_config(env)
    assert config == {"gcp:project": "acme-prod", "gcp:region": "us-central1"}


def test_gcp_target_stack_config_falls_back_to_env_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from skaal.binding.model import Environment

    env = Environment(name="prod", target=Target.GCP, region="us-central1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "acme-from-env")

    config = TARGET.stack_config(env)

    assert config == {"gcp:project": "acme-from-env", "gcp:region": "us-central1"}


def test_gcp_target_lookup_returns_callable_or_none() -> None:
    for backend in TARGET.supported_backends():
        assert callable(TARGET.lookup_synth(backend))
    assert TARGET.lookup_synth("not-a-real-backend") is None


def test_gcp_synth_classes_satisfy_the_module_contract() -> None:
    from skaal.deploy._protocol import SynthModule
    from skaal.deploy.gcp.bigquery import BigQuerySynth
    from skaal.deploy.gcp.cloud_run_fn import CloudRunFunctionSynth
    from skaal.deploy.gcp.cloud_scheduler import CloudSchedulerSynth
    from skaal.deploy.gcp.cloud_tasks import CloudTasksWorkerSynth
    from skaal.deploy.gcp.firestore import FirestoreSynth
    from skaal.deploy.gcp.gcs import GcsSynth
    from skaal.deploy.gcp.postgres import CloudSqlPostgresSynth
    from skaal.deploy.gcp.pubsub import PubsubChannelSynth
    from skaal.deploy.gcp.secrets import SecretManagerSynth

    synth_classes = [
        BigQuerySynth,
        CloudRunFunctionSynth,
        CloudSchedulerSynth,
        CloudTasksWorkerSynth,
        FirestoreSynth,
        GcsSynth,
        CloudSqlPostgresSynth,
        PubsubChannelSynth,
        SecretManagerSynth,
    ]
    for cls in synth_classes:
        assert issubclass(cls, SynthModule), f"{cls.__name__} not a SynthModule"
        assert hasattr(cls, "SPEC"), f"{cls.__name__} missing SPEC"
        assert cls.SPEC.backends, f"{cls.__name__} SPEC.backends is empty"
        assert cls.SPEC.kinds, f"{cls.__name__} SPEC.kinds is empty"


def test_cloud_run_subclasses_share_the_base_scaffold() -> None:
    from skaal.deploy.gcp._cloud_run import CloudRunSynth
    from skaal.deploy.gcp.cloud_run_fn import CloudRunFunctionSynth
    from skaal.deploy.gcp.cloud_scheduler import CloudSchedulerSynth
    from skaal.deploy.gcp.cloud_tasks import CloudTasksWorkerSynth

    for cls in (CloudRunFunctionSynth, CloudSchedulerSynth, CloudTasksWorkerSynth):
        assert issubclass(cls, CloudRunSynth)
