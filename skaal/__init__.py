"""Skaal — a Python framework where the application code is the infrastructure declaration.

This is the `0.4.0a0` line. The `0.3.x` constraint-solver surface (Z3, TOML
catalogs, `Latency` / `Durability` / `AccessPattern`, `@app.handler`,
`@app.scale`, `@app.shared`) has been removed per ADR 028. The inference
(`skaal.inference`), binding (`skaal.binding`), typed `Backend` tokens, and
`FunctionRef` typing contract land in Phases 2-5; until then the public
surface is a strict subset of the eventual `__all__` in ADR 028 §8.
"""

from skaal import types
from skaal._logging import ensure_null_handler as _ensure_null_handler
from skaal.app import App
from skaal.blob import BlobStore
from skaal.channel import Channel
from skaal.components import ExternalQueue, ExternalStorage
from skaal.decorators import (
    function,
    storage,
)
from skaal.module import Module, ModuleExport
from skaal.relational import ensure_schema as ensure_relational_schema
from skaal.relational import open_session as open_relational_session
from skaal.schedule import Cron, Every, Schedule, ScheduleContext
from skaal.secrets import Secret, SecretRegistry
from skaal.storage import Store
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
    "BeforeInvoke",
    "BlobObject",
    "BlobStore",
    "Bulkhead",
    "Channel",
    "CircuitBreaker",
    "Cron",
    "Duration",
    "Every",
    "ExternalQueue",
    "ExternalStorage",
    "InvokeContext",
    "JobHandle",
    "JobResult",
    "JobSpec",
    "JobStatus",
    "Module",
    "ModuleExport",
    "Page",
    "RateLimitPolicy",
    "Retention",
    "RetryPolicy",
    "Schedule",
    "ScheduleContext",
    "SecondaryIndex",
    "Secret",
    "SecretRegistry",
    "Store",
    "ensure_relational_schema",
    "function",
    "open_relational_session",
    "storage",
    "types",
]

__version__ = "0.4.0a0"
