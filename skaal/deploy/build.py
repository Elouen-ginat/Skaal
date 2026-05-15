"""`build_artefacts(bound, app, env)` — render Jinja2 templates to disk.

`skaal build` produces the per-Lambda Dockerfile, handler entry point,
boot-time setup, and requirements lockfile for each `BoundResource` whose
backend needs a deploy artefact. The output tree mirrors the bound plan:

```
./.skaal/build/<env_name>/
├── manifest.json                 # build_fingerprint, env, resource ids
└── <resource_id_slug>/
    ├── Dockerfile
    ├── handler.py
    ├── bootstrap.py
    └── requirements.txt
```

The templating step is pure: no Pulumi import, no AWS API access, no
network. `skaal deploy` consumes the rendered tree.

The function is target-agnostic at the entry point — it dispatches on
`Environment.target` to pick the right template subdirectory. Phase 4
ships AWS templates only; the GCP tree lands in a 0.4.x point release
(ADR 032 §"Out of scope").
"""

from __future__ import annotations

import importlib.resources as resources
import json
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from skaal.binding.model import BoundPlan, BoundResource, Environment, Target
from skaal.errors import BuildError, MissingExtraError

if TYPE_CHECKING:
    from skaal.app import App


_LAMBDA_KINDS = frozenset({"function", "asgi_service", "schedule", "job"})


def build_artefacts(
    bound: BoundPlan,
    app: App,
    env: Environment,
    *,
    out_dir: Path | None = None,
    requirements: Iterable[str] | None = None,
    app_target: str | None = None,
    python_version: str = "3.11",
) -> Path:
    """Render every deploy artefact `bound` needs into ``out_dir``.

    Args:
        bound: The bound plan to render. Resources whose backend does not
            need a build artefact (e.g. `Sqlite`, `DynamoDB`) are skipped.
        app: The live `App` (used only for the package-import path).
        env: The active environment. ``env.target`` picks the template
            subdirectory.
        out_dir: Destination directory. Defaults to
            ``./.skaal/build/<env.name>``.
        requirements: Extra pip requirements rendered into
            ``requirements.txt``. Defaults to a minimal set covering the
            skaal runtime + the AWS extras.
        app_target: The ``module:attribute`` reference the generated
            ``bootstrap.py`` imports. Defaults to ``<app.__module__>:app``.
        python_version: Python minor version embedded in the Dockerfile
            base image (e.g. ``"3.11"``).

    Returns:
        The directory the artefacts were written to (the resolved
        ``out_dir``).

    Raises:
        BuildError: If the env target is not supported, no Lambda-shaped
            resources are present, or template rendering fails.
        MissingExtraError: If the templating dependency (`jinja2`) is not
            installed.
    """
    if env.target is not Target.AWS:
        raise BuildError(
            f"`skaal build` only supports target {Target.AWS.value!r} in 0.4.0-alpha; "
            f"env {env.name!r} targets {env.target.value!r}. "
            "GCP support lands in a 0.4.x point release per ADR 032."
        )

    env_module = _Jinja2(_template_root(env.target))
    resolved_out = out_dir or Path(".skaal") / "build" / env.name
    resolved_out.mkdir(parents=True, exist_ok=True)

    target_resources = tuple(_lambda_resources(bound.resources))
    if not target_resources:
        raise BuildError(
            "No Lambda-shaped resources to build. Add at least one "
            "`@app.function`, `@app.schedule`, `@app.job`, or `app.mount(...)` "
            "to the app."
        )

    resolved_app_target = app_target or _default_app_target(app)
    resolved_requirements = list(requirements) if requirements is not None else _default_requirements()

    manifest_resources: list[dict[str, Any]] = []
    manifest: dict[str, Any] = {
        "version": 1,
        "app": bound.app,
        "environment": env.name,
        "target": env.target.value,
        "app_fingerprint": bound.app_fingerprint,
        "bound_fingerprint": bound.bound_fingerprint,
        "resources": manifest_resources,
    }

    for resource in target_resources:
        slug = _slug(resource.inferred.id)
        resource_dir = resolved_out / slug
        resource_dir.mkdir(parents=True, exist_ok=True)
        context = {
            "app_name": bound.app,
            "env_name": env.name,
            "target": env.target.value,
            "user_package": _user_package(app),
            "app_target": resolved_app_target,
            "python_version": python_version,
            "resource_id": resource.inferred.id,
            "resource_kind": resource.inferred.kind.value,
            "backend": resource.backend,
            "bound_fingerprint": bound.bound_fingerprint,
            "app_fingerprint": bound.app_fingerprint,
            "requirements": resolved_requirements,
        }
        for template_name, output_name in (
            ("Dockerfile.j2", "Dockerfile"),
            ("handler.py.j2", "handler.py"),
            ("bootstrap.py.j2", "bootstrap.py"),
            ("requirements.txt.j2", "requirements.txt"),
        ):
            template = env_module.get_template(template_name)
            rendered = template.render(**context)
            (resource_dir / output_name).write_text(rendered, encoding="utf-8")

        manifest_resources.append(
            {
                "id": resource.inferred.id,
                "kind": resource.inferred.kind.value,
                "backend": resource.backend,
                "slug": slug,
                "external": resource.external,
            }
        )

    (resolved_out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return resolved_out


def _lambda_resources(resources_in: Iterable[BoundResource]) -> Iterable[BoundResource]:
    for resource in resources_in:
        if resource.external:
            continue
        if resource.inferred.kind.value in _LAMBDA_KINDS:
            yield resource


def _slug(resource_id: str) -> str:
    """Return a filesystem-safe slug derived from a resource id.

    The slug keeps the bare class/function name plus a short hash of the
    full id so two same-named resources in different modules do not
    collide on disk.
    """
    import hashlib

    bare = resource_id.rsplit(":", 1)[-1].rsplit(".", 1)[-1] or "resource"
    digest = hashlib.sha256(resource_id.encode("utf-8")).hexdigest()[:8]
    safe = "".join(c if c.isalnum() or c in {"-", "_"} else "_" for c in bare)
    return f"{safe}-{digest}"


def _user_package(app: App) -> str:
    """Return the importable package the app lives under.

    Used by the Dockerfile to know which directory to copy in. For
    ``examples.todo_api`` (module form) the package is ``examples``; for
    ``my_service.app`` it is ``my_service``.
    """
    module = getattr(type(app), "__module__", "") or ""
    return module.split(".", 1)[0] if module else "skaal_user_app"


def _default_app_target(app: App) -> str:
    """Best-effort ``module:attribute`` reference for ``app``.

    The CLI passes an explicit ``--app-target`` value when invoked, so
    this is a fallback for programmatic callers.
    """
    module = getattr(type(app), "__module__", "") or "__main__"
    return f"{module}:app"


def _default_requirements() -> list[str]:
    return [
        "skaal[runtime,aws]",
        "mangum>=0.17",
    ]


def _template_root(target: Target) -> Path:
    """Resolve the on-disk Jinja2 template directory for ``target``.

    Templates ship in the wheel under ``skaal/deploy/templates/<target>``;
    ``importlib.resources`` returns a `Path` traversable for both
    development checkouts and installed wheels.
    """
    with resources.as_file(
        resources.files("skaal.deploy.templates") / target.value
    ) as path:
        if not path.is_dir():
            raise BuildError(
                f"No deploy templates packaged for target {target.value!r}. "
                "Expected `skaal/deploy/templates/{target}/` in the wheel."
            )
        # `resources.as_file` exits the context immediately for filesystem
        # packages, returning the same path; the directory is stable for
        # the duration of the build call.
        return path


class _Jinja2:
    """Thin wrapper around `jinja2.Environment` that surfaces a clean error.

    ``jinja2`` is a tiny pure-Python dependency, but until it lands in the
    core requirements the import is wrapped so users get a `MissingExtraError`
    instead of an opaque `ImportError`.
    """

    def __init__(self, template_root: Path) -> None:
        try:
            from jinja2 import Environment, FileSystemLoader, StrictUndefined
        except ImportError as exc:  # pragma: no cover - exercised in CI matrix
            raise MissingExtraError(
                "`skaal build` requires jinja2. Install it with "
                "`pip install jinja2` (or via the `skaal[deploy]` extra)."
            ) from exc
        # Autoescape is intentionally disabled: the templates render
        # Dockerfiles, Python source, and requirements.txt entries — not
        # HTML. Escaping would corrupt the output (e.g. mangling `>=` in a
        # pip constraint). Template inputs are fully framework-controlled
        # (resource IDs, fingerprints, the bound plan); no user-supplied
        # request data flows through this rendering path.
        self._env: Any = Environment(  # nosec B701
            loader=FileSystemLoader(str(template_root)),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )

    def get_template(self, name: str) -> Any:
        return self._env.get_template(name)


__all__ = ["build_artefacts"]
