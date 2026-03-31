"""App — the central registry for a Skim application."""

from __future__ import annotations

import inspect
from typing import Any, Callable, TypeVar

from skim.types import (
    AccessPattern,
    Compute,
    ComputeType,
    Consistency,
    DecommissionPolicy,
    Durability,
    Latency,
    Scale,
    ScaleStrategy,
    Throughput,
)

F = TypeVar("F", bound=Callable[..., Any])


class App:
    """
    Central registry for a Skim application.

    Collects all annotated storage classes, agents, functions, and the deploy
    configuration. The CLI commands (skim plan, skim deploy, …) operate on this
    registry.

    Usage::

        app = App("my-service")

        @app.storage(read_latency="< 5ms", durability="persistent")
        class Profiles(skim.Map[str, Profile]):
            pass

        @app.agent(persistent=True)
        class Customer(Agent):
            score: float = 0.0

        @app.function(compute=Compute(latency="< 200ms"))
        async def predict(customer_id: str) -> float:
            ...
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._storage: dict[str, Any] = {}   # name → annotated class
        self._agents: dict[str, Any] = {}    # name → annotated class
        self._functions: dict[str, Any] = {} # name → annotated function
        self._deploy_config: dict[str, Any] = {}

    # ── Decorators ─────────────────────────────────────────────────────────

    def storage(
        self,
        *,
        read_latency: Latency | str | None = None,
        write_latency: Latency | str | None = None,
        durability: Durability | str = Durability.PERSISTENT,
        size_hint: str | None = None,
        access_pattern: AccessPattern | str = AccessPattern.RANDOM_READ,
        write_throughput: Throughput | str | None = None,
        residency: str | None = None,
        retention: str | None = None,
        auto_optimize: bool = False,
        decommission_policy: DecommissionPolicy | None = None,
    ) -> Callable[[type], type]:
        """Register a storage class with infrastructure constraints."""
        from skim.decorators import storage as _storage_dec

        outer = _storage_dec(
            read_latency=read_latency,
            write_latency=write_latency,
            durability=durability,
            size_hint=size_hint,
            access_pattern=access_pattern,
            write_throughput=write_throughput,
            residency=residency,
            retention=retention,
            auto_optimize=auto_optimize,
            decommission_policy=decommission_policy,
        )

        def decorator(cls: type) -> type:
            annotated = outer(cls)
            self._storage[cls.__name__] = annotated
            return annotated

        return decorator

    def agent(self, *, persistent: bool = True) -> Callable[[type], type]:
        """Register an agent class."""
        from skim.decorators import agent as _agent_dec

        outer = _agent_dec(persistent=persistent)

        def decorator(cls: type) -> type:
            annotated = outer(cls)
            self._agents[cls.__name__] = annotated
            return annotated

        return decorator

    def function(
        self,
        *,
        compute: Compute | None = None,
        scale: Scale | None = None,
    ) -> Callable[[F], F]:
        """Register a compute function with optional constraints and scaling."""
        from skim.decorators import compute as _compute_dec, scale as _scale_dec

        def decorator(fn: F) -> F:
            if compute is not None:
                fn.__skim_compute__ = compute  # type: ignore[attr-defined]
            if scale is not None:
                fn.__skim_scale__ = scale  # type: ignore[attr-defined]
            self._functions[fn.__name__] = fn
            return fn

        return decorator

    def deploy(
        self,
        *,
        target: str = "k8s",
        region: str | None = None,
        min_instances: int = 1,
        max_instances: int = 10,
        scale_on: str | None = None,
        overflow: str | None = None,
    ) -> Callable[[F], F]:
        """Register the deploy target for this application."""
        from skim.decorators import deploy as _deploy_dec

        outer = _deploy_dec(
            target=target,
            region=region,
            min_instances=min_instances,
            max_instances=max_instances,
            scale_on=scale_on,
            overflow=overflow,
        )

        def decorator(fn: F) -> F:
            annotated = outer(fn)
            self._deploy_config = annotated.__skim_deploy__  # type: ignore[attr-defined]
            return annotated

        return decorator

    # ── Introspection ───────────────────────────────────────────────────────

    def describe(self) -> dict[str, Any]:
        """Return a structured description of the registered components."""
        return {
            "name": self.name,
            "storage": list(self._storage.keys()),
            "agents": list(self._agents.keys()),
            "functions": list(self._functions.keys()),
            "deploy": self._deploy_config,
        }

    def __repr__(self) -> str:
        return (
            f"App({self.name!r}, "
            f"storage={list(self._storage)}, "
            f"agents={list(self._agents)}, "
            f"functions={list(self._functions)})"
        )
