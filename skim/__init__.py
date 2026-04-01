"""
Skim — Infrastructure as Constraints.

Write it once. Scale it with a word.
"""

from skim.app import App
from skim.module import Module, ModuleExport
from skim.agent import Agent, agent
from skim.channel import Channel
from skim.decorators import (
    compute,
    deploy,
    handler,
    scale,
    shared,
    storage,
)
from skim.patterns import EventLog, Outbox, Projection, Saga, SagaStep
from skim.components import (
    APIGateway,
    AuthConfig,
    ExternalObservability,
    ExternalQueue,
    ExternalStorage,
    Proxy,
    Route,
)
from skim.types import (
    Bulkhead,
    CircuitBreaker,
    RateLimitPolicy,
    RetryPolicy,
)
from skim import types

__all__ = [
    # Core
    "App",
    "Module",
    "ModuleExport",
    "Agent",
    "Channel",
    # Decorators
    "agent",
    "compute",
    "deploy",
    "handler",
    "scale",
    "shared",
    "storage",
    # Patterns
    "EventLog",
    "Outbox",
    "Projection",
    "Saga",
    "SagaStep",
    # Components
    "APIGateway",
    "AuthConfig",
    "ExternalObservability",
    "ExternalQueue",
    "ExternalStorage",
    "Proxy",
    "Route",
    # Resilience types
    "Bulkhead",
    "CircuitBreaker",
    "RateLimitPolicy",
    "RetryPolicy",
    # Type namespace
    "types",
]

__version__ = "0.1.0"
