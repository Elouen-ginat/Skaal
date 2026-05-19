"""Typed configuration for the GCP deploy target (ADR 042).

Mirrors `skaal.deploy.aws._config.AwsConfig`: every numeric / string default
the GCP synth modules apply lives in one of the pydantic models below.
``GcpConfig.from_env(env)`` overlays
``env.backends["gcp"].options.<section>`` from `skaal.toml` on top.

Example `skaal.toml` overlay:

```toml
[env.prod]
target = "gcp"
region = "us-central1"

[env.prod.backends.gcp]
project = "acme-prod"

[env.prod.backends.gcp.options.cloud_run_defaults]
memory = "1Gi"
timeout_s = 600
max_instances = 50

[env.prod.backends.gcp.options.bigquery]
location = "EU"
```
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict

from skaal.deploy._protocol import TargetConfig


class IamConfig(TargetConfig):
    """IAM scaffold knobs for Cloud Run service accounts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provision_service_account: bool = False
    service_account_display_name: str = "Skaal Cloud Run service account"
    # Roles attached to every Skaal service account. Override per-deploy via
    # `skaal.toml` when stricter scoping is required.
    base_roles: tuple[str, ...] = (
        "roles/logging.logWriter",
        "roles/monitoring.metricWriter",
    )
    # Per-storage-backend roles attached when a peer of that backend is wired
    # into the same Cloud Run service.
    storage_roles: dict[str, str] = {
        "firestore": "roles/datastore.user",
        "gcs": "roles/storage.objectAdmin",
        "pubsub": "roles/pubsub.publisher",
        "postgres": "roles/cloudsql.client",
        "bigquery": "roles/bigquery.dataEditor",
        "gcp-secret-manager": "roles/secretmanager.secretAccessor",
    }


class ArtifactRegistryConfig(TargetConfig):
    """Artifact Registry knobs for Cloud Run container images."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    location: str = "us"
    format: Literal["DOCKER", "MAVEN", "NPM", "PYTHON"] = "DOCKER"
    immutable_tags: bool = False


class CloudRunConfig(TargetConfig):
    """Defaults for plain `function`-kind Cloud Run services."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timeout_s: int = 300
    memory: str = "512Mi"
    cpu: str = "1"
    max_instances: int = 10
    min_instances: int = 0
    port: int = 8080
    ingress: Literal["INGRESS_TRAFFIC_ALL", "INGRESS_TRAFFIC_INTERNAL_ONLY"] = "INGRESS_TRAFFIC_ALL"


class CloudRunAsgiConfig(TargetConfig):
    """Defaults for `asgi_service`-kind Cloud Run services (web apps)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timeout_s: int = 300
    memory: str = "1Gi"
    cpu: str = "1"
    max_instances: int = 20


class CloudRunJobConfig(TargetConfig):
    """Defaults for `job`-kind Cloud Run worker services (Cloud Tasks targets)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timeout_s: int = 600
    memory: str = "512Mi"
    cpu: str = "1"
    max_instances: int = 10


class FirestoreConfig(TargetConfig):
    """Defaults for `gcp.firestore.Database` resources (STORE kind)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    location_id: str = "nam5"
    type_: Literal["FIRESTORE_NATIVE", "DATASTORE_MODE"] = "FIRESTORE_NATIVE"
    env_var_prefix: str = "SKAAL_TABLE_"


class GcsConfig(TargetConfig):
    """Defaults for `gcp.storage.Bucket` resources (BLOB kind)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    location: str = "US"
    storage_class: Literal["STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"] = "STANDARD"
    uniform_bucket_level_access: bool = True
    env_var_prefix: str = "SKAAL_BUCKET_"


class PubsubConfig(TargetConfig):
    """Defaults for `gcp.pubsub.Topic` resources (CHANNEL kind)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_retention_duration: str = "86400s"
    env_var_prefix: str = "SKAAL_CHANNEL_"
    env_var_suffix: str = "_TOPIC"


class SecretsConfig(TargetConfig):
    """Defaults for `gcp.secretmanager.Secret` resources."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    replication: Literal["automatic", "user_managed"] = "automatic"
    user_managed_locations: tuple[str, ...] = ()
    env_var_prefix: str = "SKAAL_SECRET_"
    env_var_suffix: str = "_NAME"


class PostgresConfig(TargetConfig):
    """Defaults for `gcp.sql.DatabaseInstance` (Cloud SQL Postgres)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    database_version: str = "POSTGRES_16"
    edition: Literal["ENTERPRISE", "ENTERPRISE_PLUS"] = "ENTERPRISE"
    tier: str = "db-f1-micro"
    db_name: str = "skaal"
    username: str = "skaal"
    deletion_protection: bool = False
    env_var_prefix: str = "SKAAL_DB_"
    env_var_conn_suffix: str = "_CONN"
    env_var_secret_suffix: str = "_SECRET"


class BigQueryConfig(TargetConfig):
    """Defaults for `gcp.bigquery.Dataset` / `Table` resources."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    location: str = "US"
    delete_contents_on_destroy: bool = True
    env_var_prefix: str = "SKAAL_BQ_"
    env_var_dataset_suffix: str = "_DATASET"
    env_var_project_suffix: str = "_PROJECT"


class CloudSchedulerConfig(TargetConfig):
    """Defaults for `gcp.cloudscheduler.Job` (SCHEDULE kind)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fallback_schedule: str = "0 * * * *"
    time_zone: str = "Etc/UTC"
    http_method: Literal["GET", "POST"] = "POST"


class CloudTasksConfig(TargetConfig):
    """Defaults for `gcp.cloudtasks.Queue` (JOB kind)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    location: str = "us-central1"
    max_dispatches_per_second: float = 10.0
    max_concurrent_dispatches: int = 100
    max_attempts: int = 3
    env_var_prefix: str = "SKAAL_JOB_"
    env_var_queue_suffix: str = "_QUEUE"


class GcpConfig(TargetConfig):
    """Aggregated GCP target config — every sub-config is TOML-overrideable.

    Constructed once per `Environment` via
    `GcpTarget.config_for(env) → GcpConfig.from_env(env)`; synth functions
    read fields off `ctx.config.<section>`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    iam: IamConfig = IamConfig()
    artifact_registry: ArtifactRegistryConfig = ArtifactRegistryConfig()
    cloud_run_defaults: CloudRunConfig = CloudRunConfig()
    cloud_run_asgi_defaults: CloudRunAsgiConfig = CloudRunAsgiConfig()
    cloud_run_job_defaults: CloudRunJobConfig = CloudRunJobConfig()
    firestore: FirestoreConfig = FirestoreConfig()
    gcs: GcsConfig = GcsConfig()
    pubsub: PubsubConfig = PubsubConfig()
    secrets: SecretsConfig = SecretsConfig()
    postgres: PostgresConfig = PostgresConfig()
    bigquery: BigQueryConfig = BigQueryConfig()
    cloud_scheduler: CloudSchedulerConfig = CloudSchedulerConfig()
    cloud_tasks: CloudTasksConfig = CloudTasksConfig()


__all__ = [
    "ArtifactRegistryConfig",
    "BigQueryConfig",
    "CloudRunAsgiConfig",
    "CloudRunConfig",
    "CloudRunJobConfig",
    "CloudSchedulerConfig",
    "CloudTasksConfig",
    "FirestoreConfig",
    "GcpConfig",
    "GcsConfig",
    "IamConfig",
    "PostgresConfig",
    "PubsubConfig",
    "SecretsConfig",
]
