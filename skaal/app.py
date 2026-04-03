"""App — the central registry for a Skaal application."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from skaal.module import Module, ModuleExport

F = TypeVar("F", bound=Callable[..., Any])


class App(Module):
    """
    Central registry for a Skaal application.

    ``App`` extends ``Module`` with HTTP mounting (``mount()``).  All storage,
    agent, function, channel, pattern, and attach methods are inherited from
    ``Module``.

    Deployment target and region are environment concerns — they are passed to
    ``skaal deploy`` via CLI flags or environment variables (``SKAAL_TARGET``,
    ``SKAAL_REGION``), not declared in application code.  Scaling policy
    (min/max instances, concurrency) lives in the catalog's
    ``[compute.X.deploy]`` section so it can be overridden per environment
    without touching source code.

    Usage::

        app = App("my-service")

        @app.storage(read_latency="< 5ms", durability="persistent")
        class Profiles(Map[str, Profile]):
            pass

        @app.function()
        async def predict(customer_id: str) -> float:
            ...
    """

    # ── HTTP mounting ──────────────────────────────────────────────────────

    def mount(self, module: Module, *, prefix: str) -> ModuleExport:
        """
        Embed a Module AND map its HTTP-serving functions under a URL prefix.

        Equivalent to ``app.use(module)`` but additionally registers route
        prefix mappings so the deploy engine wires the proxy / API gateway
        correctly.

        Usage::

            app.mount(auth, prefix="/auth")
            # auth's functions are now accessible at /auth/*
        """
        exports = self.use(module)
        # Record the prefix mapping for the deploy engine
        ns = exports.namespace or module.name
        if not hasattr(self, "_mounts"):
            self._mounts: dict[str, str] = {}
        self._mounts[ns] = prefix
        return exports

    # ── Introspection ──────────────────────────────────────────────────────

    def describe(self) -> dict[str, Any]:
        base = super().describe()
        base["mounts"] = getattr(self, "_mounts", {})
        return base

    def __repr__(self) -> str:
        return (
            f"App({self.name!r}, "
            f"storage={list(self._storage)}, "
            f"agents={list(self._agents)}, "
            f"functions={list(self._functions)})"
        )
