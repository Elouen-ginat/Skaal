"""Sequential orchestration of multi-app Skaal projects.

The orchestrator consumes a `ProjectGraph` and runs the existing per-app
verbs (`plan`, `build`, `deploy`, `destroy`) in topological order,
shuffling cross-app environment variables between steps so that
`AppRef("backend")` resolves automatically in downstream apps.

Failures are fail-fast: the first non-zero step aborts the run and
leaves whatever upstream apps were already deployed up. The caller (CLI
or `skaal.api`) receives a list of per-app `OrchestrationStep` records
describing what happened.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from skaal.project_lock import PROJECT_LOCK_FILE_NAME, ProjectLock
from skaal.types.project import AppNode, ProjectGraph

log = logging.getLogger("skaal.cli")


@dataclass
class OrchestrationStep:
    """Per-app result of a multi-app orchestration run."""

    name: str
    target: str
    success: bool
    url: str | None = None
    outputs: dict[str, str] = field(default_factory=dict)
    error: str | None = None


# ── Environment helpers ───────────────────────────────────────────────────────


def _env_for_consumer(
    graph: ProjectGraph,
    consumer: str,
    upstream_urls: dict[str, str],
) -> dict[str, str]:
    """Return env updates that wire upstream URLs into *consumer*."""
    updates: dict[str, str] = {}
    for env_var, upstream_name in graph.expose_env_for(consumer).items():
        url = upstream_urls.get(upstream_name)
        if url:
            updates[env_var] = url
    return updates


def hydrate_env_from_lock(
    graph: ProjectGraph,
    consumer: str,
    *,
    lock_path: Path | str = PROJECT_LOCK_FILE_NAME,
) -> dict[str, str]:
    """Pull upstream URLs from `plan.skaal.project.lock` for partial deploys.

    Used when running `skaal deploy <consumer>` without `--all`: the
    upstream apps may have been deployed previously; we read their last
    URLs from the project lock and inject them into the environment of
    the current process.

    Returns:
        The dict of env vars actually injected (subset of the consumer's
        declared exposes — keys without a recorded ``last_url`` are skipped).

    Raises:
        RuntimeError: If any upstream listed in ``edges[consumer]`` has no
            ``last_url`` in the lock file. Messages tell the user to run
            `skaal deploy <upstream>` or `--all` first.
    """
    lock = ProjectLock.read(lock_path)
    upstream_urls: dict[str, str] = {}
    missing: list[str] = []
    for upstream in graph.edges.get(consumer, frozenset()):
        url = lock.url_for(upstream)
        if url is None:
            missing.append(upstream)
            continue
        upstream_urls[upstream] = url

    if missing:
        names = ", ".join(repr(n) for n in missing)
        raise RuntimeError(
            f"Cannot deploy {consumer!r}: upstream app(s) {names} have no "
            f"recorded URL in {PROJECT_LOCK_FILE_NAME}. Run "
            f"`skaal deploy <upstream>` or `skaal deploy --all` first."
        )

    updates = _env_for_consumer(graph, consumer, upstream_urls)
    os.environ.update(updates)
    return updates


# ── Single-app orchestration steps (plan + build + deploy) ────────────────────


def _run_node(
    node: AppNode,
    *,
    upstream_urls: dict[str, str],
    graph: ProjectGraph,
    yes: bool,
) -> OrchestrationStep:
    """Plan, build, and deploy one app, capturing its URL."""
    from skaal import api

    env_updates = _env_for_consumer(graph, node.name, upstream_urls)
    saved: dict[str, str | None] = {k: os.environ.get(k) for k in env_updates}
    os.environ.update(env_updates)

    try:
        node.out.mkdir(parents=True, exist_ok=True)
        plan_path = node.out / "plan.skaal.lock"
        log.info("[%s] planning -> %s", node.name, node.target)
        api.plan(
            node.module,
            target=node.target,
            catalog=node.catalog,
            write=True,
            output_path=plan_path,
        )

        log.info("[%s] building artifacts in %s", node.name, node.out)
        api.build(
            plan=plan_path,
            output_dir=node.out,
            region=node.region,
            stack=node.stack,
        )

        log.info("[%s] deploying stack %s", node.name, node.stack)
        outputs = api.deploy(
            artifacts_dir=node.out,
            stack=node.stack,
            region=node.region,
            gcp_project=node.gcp_project,
            yes=yes,
        )

        url = _select_app_url(outputs)
        if url:
            node.out.mkdir(parents=True, exist_ok=True)
            (node.out / "url.txt").write_text(url + "\n", encoding="utf-8")
            upstream_urls[node.name] = url

        return OrchestrationStep(
            name=node.name,
            target=node.target,
            success=True,
            url=url,
            outputs=outputs,
        )
    except Exception as exc:
        log.error("[%s] %s", node.name, exc)
        return OrchestrationStep(
            name=node.name,
            target=node.target,
            success=False,
            error=str(exc),
        )
    finally:
        # Restore the previous environment so steps are isolated except for
        # the explicit URL forwarding below.
        for key, prior in saved.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior


def _select_app_url(outputs: dict[str, str]) -> str | None:
    """Pick the most likely "service URL" out of Pulumi outputs.

    AWS Lambda + API Gateway exposes ``apiUrl``; GCP Cloud Run exposes
    ``serviceUrl``; the local target uses ``serviceUrl`` too. Fall back to
    any single ``*Url`` key if none of those match.
    """
    for key in ("apiUrl", "serviceUrl", "url"):
        value = outputs.get(key)
        if value:
            return value
    url_keys = [k for k in outputs if k.lower().endswith("url")]
    if len(url_keys) == 1:
        return outputs[url_keys[0]]
    return None


# ── Public entrypoints ────────────────────────────────────────────────────────


def deploy_all(
    graph: ProjectGraph,
    *,
    yes: bool = True,
    lock_path: Path | str = PROJECT_LOCK_FILE_NAME,
    only: Iterable[str] | None = None,
) -> list[OrchestrationStep]:
    """Plan + build + deploy every app in *graph* in topological order.

    Args:
        graph:     The resolved project graph.
        yes:       Pass ``--yes`` to ``pulumi up`` (non-interactive).
        lock_path: Where to write the project lock file.
        only:      Restrict execution to a subset of apps. Upstream URLs
                   for apps outside the set are read from the lock file.

    Returns:
        One `OrchestrationStep` per app actually run, in execution order.
    """
    selected = set(only) if only is not None else None
    upstream_urls: dict[str, str] = {}
    steps: list[OrchestrationStep] = []
    lock = ProjectLock.read(lock_path)

    # Seed upstream_urls from the lock so partial runs can satisfy
    # downstream consumers without redeploying upstreams.
    for name, entry in lock.apps.items():
        if entry.last_url:
            upstream_urls[name] = entry.last_url

    for name in graph.order:
        node = graph.apps[name]
        if selected is not None and name not in selected:
            continue
        step = _run_node(node, upstream_urls=upstream_urls, graph=graph, yes=yes)
        steps.append(step)
        if not step.success:
            log.error(
                "Aborting orchestration after %r failed; downstream apps not run.",
                name,
            )
            break
        lock.upsert(
            node.name,
            module=node.module,
            target=node.target,
            depends_on=list(node.depends_on),
            last_url=step.url,
            plan_lock=node.out / "plan.skaal.lock",
        )

    if any(step.success for step in steps):
        lock.write(lock_path)

    return steps


def destroy_all(
    graph: ProjectGraph,
    *,
    yes: bool = True,
    only: Iterable[str] | None = None,
) -> list[OrchestrationStep]:
    """Destroy every deployed app in reverse topological order."""
    from skaal import api

    selected = set(only) if only is not None else None
    steps: list[OrchestrationStep] = []
    for name in reversed(graph.order):
        if selected is not None and name not in selected:
            continue
        node = graph.apps[name]
        try:
            log.info("[%s] destroying stack %s", node.name, node.stack)
            api.destroy(artifacts_dir=node.out, stack=node.stack, yes=yes)
            steps.append(OrchestrationStep(name=node.name, target=node.target, success=True))
        except Exception as exc:
            log.error("[%s] %s", node.name, exc)
            steps.append(
                OrchestrationStep(
                    name=node.name,
                    target=node.target,
                    success=False,
                    error=str(exc),
                )
            )
            break
    return steps


def plan_all(
    graph: ProjectGraph,
    *,
    only: Iterable[str] | None = None,
) -> list[OrchestrationStep]:
    """Run `skaal plan` for every app, writing per-app lock files."""
    from skaal import api

    selected = set(only) if only is not None else None
    steps: list[OrchestrationStep] = []
    for name in graph.order:
        if selected is not None and name not in selected:
            continue
        node = graph.apps[name]
        try:
            node.out.mkdir(parents=True, exist_ok=True)
            api.plan(
                node.module,
                target=node.target,
                catalog=node.catalog,
                write=True,
                output_path=node.out / "plan.skaal.lock",
            )
            steps.append(OrchestrationStep(name=node.name, target=node.target, success=True))
        except Exception as exc:
            log.error("[%s] %s", node.name, exc)
            steps.append(
                OrchestrationStep(
                    name=node.name,
                    target=node.target,
                    success=False,
                    error=str(exc),
                )
            )
            break
    return steps


def build_all(
    graph: ProjectGraph,
    *,
    only: Iterable[str] | None = None,
    dev: bool = False,
) -> list[OrchestrationStep]:
    """Run `skaal build` for every app from its per-app lock file."""
    from skaal import api

    selected = set(only) if only is not None else None
    steps: list[OrchestrationStep] = []
    for name in graph.order:
        if selected is not None and name not in selected:
            continue
        node = graph.apps[name]
        try:
            api.build(
                plan=node.out / "plan.skaal.lock",
                output_dir=node.out,
                region=node.region,
                stack=node.stack,
                dev=dev,
            )
            steps.append(OrchestrationStep(name=node.name, target=node.target, success=True))
        except Exception as exc:
            log.error("[%s] %s", node.name, exc)
            steps.append(
                OrchestrationStep(
                    name=node.name,
                    target=node.target,
                    success=False,
                    error=str(exc),
                )
            )
            break
    return steps


# ── Local-dev endpoint registry ───────────────────────────────────────────────


LOCAL_ENDPOINTS_FILE = ".skaal/local-endpoints.json"


def write_local_endpoints(
    endpoints: dict[str, str],
    *,
    path: Path | str = LOCAL_ENDPOINTS_FILE,
) -> Path:
    """Persist a `{app_name: url}` map for local-dev cross-app discovery."""
    import json

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(endpoints, indent=2) + "\n", encoding="utf-8")
    return target


def read_local_endpoints(
    path: Path | str = LOCAL_ENDPOINTS_FILE,
) -> dict[str, str]:
    """Return the local endpoint registry, or an empty dict if missing."""
    import json

    target = Path(path)
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def env_from_local_endpoints(
    graph: ProjectGraph,
    consumer: str,
    *,
    path: Path | str = LOCAL_ENDPOINTS_FILE,
) -> dict[str, str]:
    """Build the env vars a single locally-running consumer needs."""
    endpoints = read_local_endpoints(path)
    return _env_for_consumer(graph, consumer, endpoints)


__all__ = [
    "LOCAL_ENDPOINTS_FILE",
    "OrchestrationStep",
    "build_all",
    "deploy_all",
    "destroy_all",
    "env_from_local_endpoints",
    "hydrate_env_from_lock",
    "plan_all",
    "read_local_endpoints",
    "write_local_endpoints",
]
