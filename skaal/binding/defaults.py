"""The per-`(ResourceKind, Target)` defaults table (ADR 028 §6.3, ADR 031 §3.5).

Pure data: one cell per `(ResourceKind, Target)` slot, naming the typed
`Backend` token Skaal picks when the resource is un-pinned and no env
override or lock entry supplies one. The table is wrapped in
``MappingProxyType`` so it cannot be mutated by a misbehaving import.

Changing a cell is an ADR-gated decision (per CLAUDE.md "Adding a new
backend"); the binding tests assert every cell is registered and every
slot is populated.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from skaal.backends._base import Backend
from skaal.backends._tokens import (
    S3,
    ApigwLambda,
    Apscheduler,
    Asyncio,
    AwsSecretsManager,
    CloudRun,
    CloudSchedulerCloudRun,
    CloudTasksCloudRun,
    DotenvSecret,
    DynamoDB,
    EventBridgeLambda,
    FilesystemBlob,
    Firestore,
    GcpSecretManager,
    Gcs,
    InProcessChannel,
    Lambda,
    Postgres,
    Pubsub,
    Sqlite,
    Sqs,
    SqsLambdaWorker,
    Uvicorn,
)
from skaal.binding.model import Target
from skaal.inference.model import ResourceKind


def _row(local: type[Backend], aws: type[Backend], gcp: type[Backend]) -> Mapping[Target, type[Backend]]:
    return MappingProxyType({Target.LOCAL: local, Target.AWS: aws, Target.GCP: gcp})


DEFAULTS: Mapping[ResourceKind, Mapping[Target, type[Backend]]] = MappingProxyType(
    {
        ResourceKind.STORE: _row(Sqlite, DynamoDB, Firestore),
        ResourceKind.RELATIONAL: _row(Sqlite, Postgres, Postgres),
        ResourceKind.BLOB: _row(FilesystemBlob, S3, Gcs),
        ResourceKind.CHANNEL: _row(InProcessChannel, Sqs, Pubsub),
        ResourceKind.FUNCTION: _row(Asyncio, Lambda, CloudRun),
        ResourceKind.ASGI_SERVICE: _row(Uvicorn, ApigwLambda, CloudRun),
        ResourceKind.SCHEDULE: _row(Apscheduler, EventBridgeLambda, CloudSchedulerCloudRun),
        ResourceKind.JOB: _row(Apscheduler, SqsLambdaWorker, CloudTasksCloudRun),
        ResourceKind.SECRET: _row(DotenvSecret, AwsSecretsManager, GcpSecretManager),
    }
)
