"""GCP-specific `skaal where` metadata and console URL builders (ADR 042)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from skaal.deploy._protocol import ConsoleUrlResolver

StackMapping = Mapping[str, Any]

GCP_CLOUDRUN_SERVICE = "gcp:cloudrunv2/service:Service"
GCP_FIRESTORE_DATABASE = "gcp:firestore/database:Database"
GCP_STORAGE_BUCKET = "gcp:storage/bucket:Bucket"
GCP_PUBSUB_TOPIC = "gcp:pubsub/topic:Topic"
GCP_SECRETMANAGER_SECRET = "gcp:secretmanager/secret:Secret"
GCP_SQL_INSTANCE = "gcp:sql/databaseInstance:DatabaseInstance"
GCP_BIGQUERY_DATASET = "gcp:bigquery/dataset:Dataset"
GCP_BIGQUERY_TABLE = "gcp:bigquery/table:Table"
GCP_CLOUDSCHEDULER_JOB = "gcp:cloudscheduler/job:Job"
GCP_CLOUDTASKS_QUEUE = "gcp:cloudtasks/queue:Queue"

WHERE_PRIMARY = 20
WHERE_FALLBACK = 10


def _project(outputs: StackMapping) -> str:
    value = outputs.get("project")
    if isinstance(value, str) and value:
        return value
    return ""


def _region(region: str | None) -> str:
    return region or "us-central1"


def _value(container: StackMapping, *keys: str) -> str:
    for key in keys:
        value = container.get(key)
        if isinstance(value, str) and value:
            return value
    raise ValueError(f"Pulumi stack state is missing the expected fields: {', '.join(keys)}.")


def cloud_run_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the GCP console URL for a Cloud Run service."""
    name = _value(outputs, "name", "id")
    project = _project(outputs)
    return (
        f"https://console.cloud.google.com/run/detail/{_region(region)}/{quote(name)}/metrics"
        + (f"?project={quote(project)}" if project else "")
    )


def firestore_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the GCP console URL for a Firestore database."""
    project = _project(outputs)
    name = _value(outputs, "name", "id")
    return f"https://console.cloud.google.com/firestore/databases/{quote(name)}/data" + (
        f"?project={quote(project)}" if project else ""
    )


def gcs_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the GCP console URL for a GCS bucket."""
    name = _value(outputs, "name", "id")
    project = _project(outputs)
    return f"https://console.cloud.google.com/storage/browser/{quote(name)}" + (
        f"?project={quote(project)}" if project else ""
    )


def pubsub_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the GCP console URL for a Pub/Sub topic."""
    name = _value(outputs, "name", "id")
    project = _project(outputs)
    return f"https://console.cloud.google.com/cloudpubsub/topic/detail/{quote(name)}" + (
        f"?project={quote(project)}" if project else ""
    )


def secret_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the GCP console URL for a Secret Manager secret."""
    name = _value(outputs, "secretId", "name", "id")
    project = _project(outputs)
    return (
        f"https://console.cloud.google.com/security/secret-manager/secret/{quote(name)}/versions"
        + (f"?project={quote(project)}" if project else "")
    )


def cloud_sql_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the GCP console URL for a Cloud SQL instance."""
    name = _value(outputs, "name", "id")
    project = _project(outputs)
    return f"https://console.cloud.google.com/sql/instances/{quote(name)}/overview" + (
        f"?project={quote(project)}" if project else ""
    )


def bigquery_dataset_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the GCP console URL for a BigQuery dataset."""
    dataset = _value(outputs, "datasetId", "name", "id")
    project = _project(outputs)
    target_project = project or "_"
    return (
        f"https://console.cloud.google.com/bigquery"
        f"?p={quote(target_project)}&d={quote(dataset)}&page=dataset"
    )


def bigquery_table_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the GCP console URL for a BigQuery table."""
    table = _value(outputs, "tableId", "name", "id")
    dataset = outputs.get("datasetId")
    project = _project(outputs)
    target_project = project or "_"
    dataset_str = dataset if isinstance(dataset, str) else ""
    return (
        f"https://console.cloud.google.com/bigquery?p={quote(target_project)}"
        f"&d={quote(dataset_str)}&t={quote(table)}&page=table"
    )


def cloud_scheduler_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the GCP console URL for a Cloud Scheduler job."""
    name = _value(outputs, "name", "id")
    project = _project(outputs)
    return (
        f"https://console.cloud.google.com/cloudscheduler/jobs/edit/{_region(region)}/{quote(name)}"
        + (f"?project={quote(project)}" if project else "")
    )


def cloud_tasks_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the GCP console URL for a Cloud Tasks queue."""
    name = _value(outputs, "name", "id")
    project = _project(outputs)
    return (
        f"https://console.cloud.google.com/cloudtasks/queue/{_region(region)}/{quote(name)}/tasks"
        + (f"?project={quote(project)}" if project else "")
    )


GCP_CONSOLE_URLS: dict[str, ConsoleUrlResolver] = {
    GCP_CLOUDRUN_SERVICE: cloud_run_console_url,
    GCP_FIRESTORE_DATABASE: firestore_console_url,
    GCP_STORAGE_BUCKET: gcs_console_url,
    GCP_PUBSUB_TOPIC: pubsub_console_url,
    GCP_SECRETMANAGER_SECRET: secret_console_url,
    GCP_SQL_INSTANCE: cloud_sql_console_url,
    GCP_BIGQUERY_DATASET: bigquery_dataset_console_url,
    GCP_BIGQUERY_TABLE: bigquery_table_console_url,
    GCP_CLOUDSCHEDULER_JOB: cloud_scheduler_console_url,
    GCP_CLOUDTASKS_QUEUE: cloud_tasks_console_url,
}


__all__ = [
    "GCP_BIGQUERY_DATASET",
    "GCP_BIGQUERY_TABLE",
    "GCP_CLOUDRUN_SERVICE",
    "GCP_CLOUDSCHEDULER_JOB",
    "GCP_CLOUDTASKS_QUEUE",
    "GCP_CONSOLE_URLS",
    "GCP_FIRESTORE_DATABASE",
    "GCP_PUBSUB_TOPIC",
    "GCP_SECRETMANAGER_SECRET",
    "GCP_SQL_INSTANCE",
    "GCP_STORAGE_BUCKET",
    "WHERE_FALLBACK",
    "WHERE_PRIMARY",
    "bigquery_dataset_console_url",
    "bigquery_table_console_url",
    "cloud_run_console_url",
    "cloud_scheduler_console_url",
    "cloud_sql_console_url",
    "cloud_tasks_console_url",
    "firestore_console_url",
    "gcs_console_url",
    "pubsub_console_url",
    "secret_console_url",
]
