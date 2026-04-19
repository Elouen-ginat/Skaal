"""skaal.runtime — runtime implementations.

:class:`LocalRuntime` runs a Skaal app in a single process with in-memory or
pluggable backends.  :class:`MeshRuntime` adds distributed routing via the
Rust ``skaal_mesh`` extension (``pip install skaal[mesh]``).  Third parties can
register their own runtime implementations via ``skaal.plugins``.
"""

from skaal.runtime.agent_registry import AgentRecord, AgentRegistry, AgentStatus
from skaal.runtime.channels import Channel, LocalChannel
from skaal.runtime.local import LocalRuntime
from skaal.runtime.state import InMemoryStateStore, StateStore

__all__ = [
    "AgentRecord",
    "AgentRegistry",
    "AgentStatus",
    "Channel",
    "InMemoryStateStore",
    "LocalChannel",
    "LocalRuntime",
    "MeshRuntime",
    "StateStore",
]


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    if name == "MeshRuntime":
        from skaal.runtime.mesh_runtime import MeshRuntime

        return MeshRuntime
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
