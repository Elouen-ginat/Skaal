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
from skaal.api import PlanChange, PlanDiff, SourceMatch
from skaal.app import App
from skaal.backends._base import Backend
from skaal.binding import (
    BackendCapabilities,
    BackendConfig,
    BackendSpec,
    Environment,
    EnvOverride,
    LockEntry,
    LockFile,
    Plan,
    PlannedResource,
    Target,
    plan,
)
from skaal.blob import BlobStore
from skaal.channel import Topic
from skaal.components import ExternalQueue, ExternalStorage
from skaal.decorators import (
    FunctionRef,
    connect,
    expose,
    storage,
)
from skaal.inference import (
    Blueprint,
    BlueprintResource,
    Edge,
    Overrides,
    ResourceKind,
    SchemaRef,
    SourceLocation,
    blueprint,
)
from skaal.module import Module, ModuleExport
from skaal.plugins import Plugin, PluginRegistry, load_plugins
from skaal.relational import Table
from skaal.schedule import Cron, Every, Schedule, ScheduleContext
from skaal.secrets import Secret, SecretRegistry
from skaal.storage import Store
from skaal.types import (
    TTL,
    BeforeInvocation,
    BlobItem,
    Bulkhead,
    CircuitBreaker,
    Duration,
    InvocationContext,
    JobHandle,
    JobResult,
    JobSpec,
    JobStatus,
    Page,
    RateLimit,
    Retention,
    Retry,
    SecondaryIndex,
)

_ensure_null_handler()

__all__ = [
    "TTL",
    "App",
    "Backend",
    "BackendCapabilities",
    "BackendConfig",
    "BackendSpec",
    "BeforeInvocation",
    "BlobItem",
    "BlobStore",
    "Blueprint",
    "BlueprintResource",
    "Bulkhead",
    "CircuitBreaker",
    "Cron",
    "Duration",
    "Edge",
    "EnvOverride",
    "Environment",
    "Every",
    "ExternalQueue",
    "ExternalStorage",
    "FunctionRef",
    "InvocationContext",
    "JobHandle",
    "JobResult",
    "JobSpec",
    "JobStatus",
    "LockEntry",
    "LockFile",
    "Module",
    "ModuleExport",
    "Overrides",
    "Page",
    "Plan",
    "PlanChange",
    "PlanDiff",
    "PlannedResource",
    "Plugin",
    "PluginRegistry",
    "RateLimit",
    "ResourceKind",
    "Retention",
    "Retry",
    "Schedule",
    "ScheduleContext",
    "SchemaRef",
    "SecondaryIndex",
    "Secret",
    "SecretRegistry",
    "SourceLocation",
    "SourceMatch",
    "Store",
    "Table",
    "Target",
    "Topic",
    "api",
    "blueprint",
    "connect",
    "expose",
    "load_plugins",
    "plan",
    "storage",
    "types",
]

__version__ = "0.4.0a0"
