"""
Skaal — Infrastructure as Constraints.

Write it once. Scale it with a word.
"""

from skaal import api, types
from skaal.agent import Agent, agent
from skaal.app import App
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
    relational,
    scale,
    shared,
    storage,
)
from skaal.module import Module, ModuleExport
from skaal.patterns import EventLog, Outbox, Projection, Saga, SagaStep
from skaal.relational import ensure_schema as ensure_relational_schema
from skaal.relational import open_session as open_relational_session
from skaal.schedule import Cron, Every, Schedule, ScheduleContext
from skaal.storage import Store
from skaal.types import (
    Bulkhead,
    CircuitBreaker,
    RateLimitPolicy,
    RetryPolicy,
)

__all__ = [
    # Python API namespace (run/plan/build/deploy/...)
    "api",
    # Core
    "App",
    "Module",
    "ModuleExport",
    "Store",
    "Agent",
    "Channel",
    # Decorators
    "agent",
    "compute",
    "handler",
    "relational",
    "scale",
    "shared",
    "storage",
    "open_relational_session",
    "ensure_relational_schema",
    # Patterns
    "EventLog",
    "Outbox",
    "Projection",
    "Saga",
    "SagaStep",
    # Components
    "APIGateway",
    "AppRef",
    "AuthConfig",
    "ExternalObservability",
    "ExternalQueue",
    "ExternalStorage",
    "Proxy",
    "Route",
    "ScheduleTrigger",
    # Schedule
    "Cron",
    "Every",
    "Schedule",
    "ScheduleContext",
    # Resilience types
    "Bulkhead",
    "CircuitBreaker",
    "RateLimitPolicy",
    "RetryPolicy",
    # Type namespace
    "types",
]

__version__ = "0.1.0"
