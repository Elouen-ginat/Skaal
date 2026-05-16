"""Skaal — a Python framework where the application code is the infrastructure declaration.

This is the `0.4.0a0` line. The `0.3.x` constraint-solver surface (Z3, TOML
catalogs, `Latency` / `Durability` / `AccessPattern`, `@app.handler`,
`@app.scale`, `@app.shared`) has been removed per ADR 028. The inference
(`skaal.inference`), binding (`skaal.binding`), typed `Backend` tokens, and
`FunctionRef` typing contract land in Phases 2-5; until then the public
surface is a strict subset of the eventual `__all__` in ADR 028 §8.
"""

from skaal import api, types
from skaal._logging import ensure_null_handler as _ensure_null_handler
from skaal.app import App
from skaal.backends._base import Backend
from skaal.binding import (
    BackendCapabilities,
    BackendConfig,
    BackendEntry,
    BoundPlan,
    BoundResource,
    Environment,
    LockEntry,
    LockFile,
    ResourceOverride,
    Target,
    bind,
    load_environment,
    load_environments,
    load_lock,
    write_lock,
)
from skaal.blob import BlobStore
from skaal.channel import Channel
from skaal.components import ExternalQueue, ExternalStorage
from skaal.decorators import (
    FunctionRef,
    external,
    function,
    storage,
)
from skaal.inference import (
    Edge,
    InferredPlan,
    InferredResource,
    ResourceKind,
    ResourceOverrides,
    SchemaRef,
    SourceLocation,
    infer,
)
from skaal.module import Module, ModuleExport
from skaal.plan_diff import PlanChange, PlanDiff
from skaal.plugins import PluginRegistry, SkaalPlugin, load_plugins
from skaal.relational import Relational
from skaal.relational import ensure_schema as ensure_relational_schema
from skaal.relational import open_session as open_relational_session
from skaal.schedule import Cron, Every, Schedule, ScheduleContext
from skaal.secrets import Secret, SecretRegistry
from skaal.storage import Store
from skaal.traceability import TraceHit
from skaal.types import (
    TTL,
    BeforeInvoke,
    BlobObject,
    Bulkhead,
    CircuitBreaker,
    Duration,
    InvokeContext,
    JobHandle,
    JobResult,
    JobSpec,
    JobStatus,
    Page,
    RateLimitPolicy,
    Retention,
    RetryPolicy,
    SecondaryIndex,
)

_ensure_null_handler()

__all__ = [
    "TTL",
    "App",
    "Backend",
    "BackendCapabilities",
    "BackendConfig",
    "BackendEntry",
    "BeforeInvoke",
    "BlobObject",
    "BlobStore",
    "BoundPlan",
    "BoundResource",
    "Bulkhead",
    "Channel",
    "CircuitBreaker",
    "Cron",
    "Duration",
    "Edge",
    "Environment",
    "Every",
    "ExternalQueue",
    "ExternalStorage",
    "FunctionRef",
    "InferredPlan",
    "InferredResource",
    "InvokeContext",
    "JobHandle",
    "JobResult",
    "JobSpec",
    "JobStatus",
    "LockEntry",
    "LockFile",
    "Module",
    "ModuleExport",
    "Page",
    "PlanChange",
    "PlanDiff",
    "PluginRegistry",
    "RateLimitPolicy",
    "Relational",
    "ResourceKind",
    "ResourceOverride",
    "ResourceOverrides",
    "Retention",
    "RetryPolicy",
    "Schedule",
    "ScheduleContext",
    "SchemaRef",
    "SecondaryIndex",
    "Secret",
    "SecretRegistry",
    "SkaalPlugin",
    "SourceLocation",
    "Store",
    "Target",
    "TraceHit",
    "api",
    "bind",
    "ensure_relational_schema",
    "external",
    "function",
    "infer",
    "load_environment",
    "load_environments",
    "load_lock",
    "load_plugins",
    "open_relational_session",
    "storage",
    "types",
    "write_lock",
]

__version__ = "0.4.0a0"
