"""Project-level types for multi-app Skaal projects.

`AppNode` is the resolved settings for one app declared under
``[tool.skaal.apps.<name>]``. `ProjectGraph` is the bundle of all
declared apps plus the topologically-sorted deploy order and the
consumer→producers edges used to inject ``SKAAL_APPREF_<NAME>_URL``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skaal.settings import SkaalSettings


def _expose_var_for(name: str) -> str:
    """Return the default exposed env var name for an app."""
    return f"SKAAL_APPREF_{name.upper().replace('-', '_')}_URL"


@dataclass(frozen=True)
class AppNode:
    """Resolved settings for one declared app in a multi-app project.

    Every field except *name*, *module*, *depends_on*, *expose*, and
    *endpoint_secret* mirrors a `SkaalSettings` field with the per-app
    overlay applied.
    """

    name: str
    module: str
    target: str
    region: str
    catalog: Path | None
    stack: str
    gcp_project: str | None
    out: Path
    depends_on: tuple[str, ...]
    expose: str
    endpoint_secret: str | None
    env: Mapping[str, str] = field(default_factory=dict)
    pre_deploy: tuple[tuple[str, ...], ...] = ()
    post_deploy: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class ProjectGraph:
    """The DAG of apps in a multi-app Skaal project.

    Built by :func:`build_project_graph` from a `SkaalSettings`. The
    constructor is light — all validation (cycle detection, undeclared
    references) happens in the builder.
    """

    apps: Mapping[str, AppNode]
    order: tuple[str, ...]
    edges: Mapping[str, frozenset[str]]

    def upstreams(self, name: str) -> tuple[AppNode, ...]:
        """Return the producer apps that *name* depends on, in declared order."""
        return tuple(self.apps[u] for u in sorted(self.edges.get(name, frozenset())))

    def downstreams(self, name: str) -> tuple[AppNode, ...]:
        """Return the consumer apps that depend on *name*."""
        return tuple(
            self.apps[other] for other in self.order if name in self.edges.get(other, frozenset())
        )

    def expose_env_for(self, consumer: str) -> dict[str, str]:
        """Return the env-var → upstream-app-name map for *consumer*.

        Values are the names of upstream apps; the orchestrator looks up the
        actual URL (from a deploy or local-port registry) when injecting.
        """
        result: dict[str, str] = {}
        for upstream in self.edges.get(consumer, frozenset()):
            node = self.apps[upstream]
            result[node.expose] = upstream
        return result


def _toposort(
    nodes: Mapping[str, AppNode],
    edges: Mapping[str, frozenset[str]],
) -> tuple[str, ...]:
    """Kahn's algorithm: produce a deterministic deploy order or raise on cycle."""
    in_degree: dict[str, int] = dict.fromkeys(nodes, 0)
    reverse: dict[str, set[str]] = {name: set() for name in nodes}
    for consumer, producers in edges.items():
        for producer in producers:
            in_degree[consumer] += 1
            reverse[producer].add(consumer)

    ready = sorted(name for name, d in in_degree.items() if d == 0)
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for downstream in sorted(reverse[current]):
            in_degree[downstream] -= 1
            if in_degree[downstream] == 0:
                ready.append(downstream)
        ready.sort()

    if len(order) != len(nodes):
        remaining = sorted(name for name in nodes if name not in order)
        raise ValueError(
            f"Cycle detected in [tool.skaal.apps] depends_on; apps still unresolved: {remaining}."
        )

    return tuple(order)


def build_project_graph(settings: SkaalSettings) -> ProjectGraph:
    """Build a `ProjectGraph` from a `SkaalSettings`.

    Validates that every ``depends_on`` name references another declared
    app, that the graph is acyclic, and resolves each app's effective
    settings via :meth:`SkaalSettings.for_app`.

    Raises:
        ValueError: If ``depends_on`` references an unknown app or the
            graph contains a cycle.
    """
    if not settings.apps:
        return ProjectGraph(apps={}, order=(), edges={})

    declared = set(settings.apps)
    nodes: dict[str, AppNode] = {}
    edges: dict[str, frozenset[str]] = {}

    for name, entry in settings.apps.items():
        unknown = [d for d in entry.depends_on if d not in declared]
        if unknown:
            raise ValueError(
                f"App {name!r} depends_on references undeclared app(s): {unknown}. "
                f"Declared apps: {sorted(declared)}."
            )

        resolved = settings.for_app(name)
        expose = entry.expose or _expose_var_for(name)
        # Per-app artifact dir defaults to ``<base.out>/<name>`` so multiple
        # apps coexist on disk; an explicit ``out`` on the app entry wins.
        resolved_out = entry.out if entry.out is not None else resolved.out / name
        nodes[name] = AppNode(
            name=name,
            module=entry.module,
            target=resolved.target,
            region=resolved.region,
            catalog=resolved.catalog,
            stack=resolved.stack,
            gcp_project=resolved.gcp_project,
            out=resolved_out,
            depends_on=tuple(entry.depends_on),
            expose=expose,
            endpoint_secret=entry.endpoint_secret,
            env=dict(resolved.env),
            pre_deploy=tuple(tuple(c) for c in resolved.pre_deploy),
            post_deploy=tuple(tuple(c) for c in resolved.post_deploy),
        )
        edges[name] = frozenset(entry.depends_on)

    order = _toposort(nodes, edges)
    return ProjectGraph(apps=nodes, order=order, edges=edges)
