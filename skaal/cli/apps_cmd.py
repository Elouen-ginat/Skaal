"""`skaal apps` — list, graph, and validate the multi-app project.

A typer sub-app that introspects the ``[tool.skaal.apps]`` table in the
nearest ``pyproject.toml`` and the ``plan.skaal.project.lock`` file
written by the orchestrator. Three verbs:

- ``skaal apps list``       — table of apps with last-deployed URL.
- ``skaal apps graph``      — ASCII / DOT / Mermaid render of the DAG.
- ``skaal apps validate``   — cycle / undeclared-name / orphan-AppRef checks.
"""

from __future__ import annotations

import json
import logging
from enum import StrEnum

import typer

from skaal.cli._errors import cli_error_boundary
from skaal.project_lock import ProjectLock
from skaal.settings import SkaalSettings
from skaal.types.project import build_project_graph

app = typer.Typer(help="Inspect the multi-app project graph.")
log = logging.getLogger("skaal.cli")


class GraphFormat(StrEnum):
    ASCII = "ascii"
    DOT = "dot"
    MERMAID = "mermaid"


def _require_apps(cfg: SkaalSettings) -> None:
    if not cfg.apps:
        raise ValueError(
            "No apps declared in [tool.skaal.apps].\n"
            "  Add at least one entry like:\n\n"
            "    [tool.skaal.apps.backend]\n"
            '    module = "myproject.backend:app"\n'
        )


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    """Default to ``skaal apps list`` when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        list_apps(json_output=False)


@app.command("list")
@cli_error_boundary
def list_apps(
    json_output: bool = typer.Option(False, "--json", help="Emit a JSON array instead of a table."),
) -> None:
    """List declared apps and their last-deployed URL."""
    cfg = SkaalSettings()
    _require_apps(cfg)
    graph = build_project_graph(cfg)
    lock = ProjectLock.read()

    rows = []
    for name in graph.order:
        node = graph.apps[name]
        entry = lock.apps.get(name)
        rows.append(
            {
                "name": name,
                "module": node.module,
                "target": node.target,
                "stack": node.stack,
                "depends_on": list(node.depends_on),
                "last_url": entry.last_url if entry else None,
                "last_deploy": entry.last_deploy if entry else None,
            }
        )

    if json_output:
        log.info(json.dumps(rows, indent=2))
        return

    log.info(f"{'app':<18} {'target':<10} {'stack':<10} {'depends_on':<20} {'last_url':<40}")
    log.info(f"{'-' * 18} {'-' * 10} {'-' * 10} {'-' * 20} {'-' * 40}")
    for row in rows:
        deps_list = row["depends_on"] if isinstance(row["depends_on"], list) else []
        deps = ",".join(deps_list) or "-"
        log.info(
            f"{row['name']:<18} {row['target']:<10} {row['stack']:<10} "
            f"{deps:<20} {(row['last_url'] or '-'):<40}"
        )


@app.command("graph")
@cli_error_boundary
def graph(
    fmt: GraphFormat = typer.Option(
        GraphFormat.ASCII,
        "--format",
        "-f",
        help="Output format: ascii | dot | mermaid.",
    ),
) -> None:
    """Render the AppRef DAG."""
    cfg = SkaalSettings()
    _require_apps(cfg)
    g = build_project_graph(cfg)

    if fmt is GraphFormat.DOT:
        log.info("digraph skaal {")
        for name in g.order:
            log.info(f'  "{name}";')
        for consumer, producers in g.edges.items():
            for producer in sorted(producers):
                log.info(f'  "{producer}" -> "{consumer}";')
        log.info("}")
    elif fmt is GraphFormat.MERMAID:
        log.info("graph LR")
        for consumer, producers in g.edges.items():
            for producer in sorted(producers):
                log.info(f"  {producer} --> {consumer}")
        for name in g.order:
            if not any(name in p for p in g.edges.values()) and not g.edges.get(name):
                log.info(f"  {name}")
    else:
        for name in g.order:
            deps = ", ".join(sorted(g.edges.get(name, frozenset())))
            arrow = f"  ({deps})" if deps else ""
            log.info(f"  {name}{arrow}")


@app.command("validate")
@cli_error_boundary
def validate() -> None:
    """Check the DAG for cycles, undeclared dependencies, and orphan `AppRef` names."""
    cfg = SkaalSettings()
    _require_apps(cfg)

    # build_project_graph already enforces cycles + undeclared dependencies.
    g = build_project_graph(cfg)
    log.info("Declared apps: %s", ", ".join(g.order))

    # Soft check: any AppRef constructed inside an app whose name is not in
    # the project. Importing the app module triggers its module-level
    # ``app.attach(AppRef("..."))`` calls, so we can scan the registered
    # components afterwards.
    from skaal import api

    declared = set(g.apps)
    warnings = 0
    for name, node in g.apps.items():
        try:
            skaal_app = api.resolve_app(node.module)
        except Exception as exc:
            log.warning("[%s] could not import %r: %s", name, node.module, exc)
            warnings += 1
            continue
        components = getattr(skaal_app, "_components", None) or {}
        for component in components.values():
            spec = getattr(component, "__skaal_component__", {}) or {}
            if spec.get("kind") != "app-ref":
                continue
            ref_name = spec.get("name")
            if ref_name and ref_name not in declared:
                log.warning(
                    "[%s] AppRef(%r) is not declared in [tool.skaal.apps]; "
                    "the URL must be set manually via base_url= or "
                    "base_url_secret=.",
                    name,
                    ref_name,
                )
                warnings += 1

    if warnings == 0:
        log.info("OK — graph is acyclic, all dependencies declared.")
