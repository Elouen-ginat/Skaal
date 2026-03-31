"""
Skim — Infrastructure as Constraints.

Write it once. Scale it with a word.
"""

from skim.app import App
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
from skim import types

__all__ = [
    "App",
    "Agent",
    "Channel",
    "agent",
    "compute",
    "deploy",
    "handler",
    "scale",
    "shared",
    "storage",
    "types",
]

__version__ = "0.1.0"
