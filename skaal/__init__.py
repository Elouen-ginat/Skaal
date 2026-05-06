"""
Skaal — Infrastructure as Constraints.

Write it once. Scale it with a word.
"""

from skaal import api, types
from skaal._logging import ensure_null_handler as _ensure_null_handler
from skaal.agent import Agent, agent
from skaal.app import App
from skaal.blob import BlobStore
from skaal.channel import Channel
from skaal.components import (
    APIGateway,
    AppRef,
    AuthConfig,
    ExternalObservability,
    ExternalQueue,
    ExternalStorage,
    Proxy,
    Route,
    ScheduleTrigger,
)
from skaal.decorators import (
    compute,
    handler,
    scale,
    shared,
    storage,
)
from skaal.module import Module, ModuleExport
from skaal.patterns import EventLog, Outbox, Projection, Saga, SagaStep
from skaal.relational import ensure_schema as ensure_relational_schema
from skaal.relational import open_session as open_relational_session
from skaal.schedule import Cron, Every, Schedule, ScheduleContext
from skaal.secrets import Secret, SecretRegistry
from skaal.storage import Store
from skaal.sync import run as sync_run
from skaal.types import (
    TTL,
    BeforeInvoke,
    BlobObject,
    Bulkhead,
    CircuitBreaker,
    Duration,
    EngineTelemetrySnapshot,
    InvokeContext,
    JobHandle,
    JobResult,
    JobSpec,
    JobStatus,
    Page,
    RateLimitPolicy,
    ReadinessState,
    RelationalMigrationOp,
    RelationalMigrationPlan,
    RelationalMigrationStatus,
    RelationalMigrationStep,
    RelationalRevision,
    Retention,
    RetryPolicy,
    SecondaryIndex,
    TelemetryConfig,
)
from skaal.vector import VectorStore

_ensure_null_handler()

__all__ = [
    "TTL",
    "APIGateway",
    "Agent",
    "App",
    "AppRef",
    "AuthConfig",
    "BeforeInvoke",
    "BlobObject",
    "BlobStore",
    "Bulkhead",
    "Channel",
    "CircuitBreaker",
    "Cron",
    "Duration",
    "EngineTelemetrySnapshot",
    "EventLog",
    "Every",
    "ExternalObservability",
    "ExternalQueue",
    "ExternalStorage",
    "InvokeContext",
    "JobHandle",
    "JobResult",
    "JobSpec",
    "JobStatus",
    "Module",
    "ModuleExport",
    "Outbox",
    "Page",
    "Projection",
    "Proxy",
    "RateLimitPolicy",
    "ReadinessState",
    "RelationalMigrationOp",
    "RelationalMigrationPlan",
    "RelationalMigrationStatus",
    "RelationalMigrationStep",
    "RelationalRevision",
    "Retention",
    "RetryPolicy",
    "Route",
    "Saga",
    "SagaStep",
    "Schedule",
    "ScheduleContext",
    "ScheduleTrigger",
    "SecondaryIndex",
    "Secret",
    "SecretRegistry",
    "Store",
    "TelemetryConfig",
    "VectorStore",
    "agent",
    "api",
    "compute",
    "ensure_relational_schema",
    "handler",
    "open_relational_session",
    "scale",
    "shared",
    "storage",
    "sync_run",
    "types",
]

__version__ = "0.3.1"
