"""`build_artefacts(bound, env, app_spec)` — render templates to disk.

`skaal build` produces the per-Lambda `Dockerfile`, `handler.py`,
`bootstrap.py`, and `pyproject.toml` for each `BoundResource` whose
backend needs a deploy artefact. The output tree mirrors the bound plan:

```
./.skaal/build/<env_name>/
├── manifest.json                 # `BuildManifest` (pydantic) on disk
└── <slug>/
    ├── Dockerfile
    ├── handler.py
    ├── bootstrap.py
    └── pyproject.toml
```

The templating step is pure: no Pulumi import, no AWS API access, no
network. `skaal deploy` consumes the rendered tree.

Every data structure that flows through this module is a pydantic model
from `skaal.deploy.models` (`BuildContext`, `BuildManifest`,
`ManifestResourceEntry`). The function is target-agnostic at the entry
point — it dispatches on `Environment.target` to pick the right template
subdirectory. Phase 4 ships AWS templates only; the GCP tree lands in a
0.4.x point release (ADR 032 §"Out of scope").
"""

from __future__ import annotations

import importlib.resources as resources
import shutil
from collections.abc import Iterable
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, Any

from skaal.binding.model import Environment, Plan, PlannedResource, Target
from skaal.deploy._naming import resource_slug
from skaal.deploy.models import (
    BuildContext,
    BuildManifest,
    ManifestResourceEntry,
)
from skaal.errors import BuildError, MissingExtraError
from skaal.inference.model import ResourceKind
from skaal.runtime.models import RuntimeBindingManifest

if TYPE_CHECKING:
    from skaal.cli._load import AppSpec


_LAMBDA_KINDS: frozenset[ResourceKind] = frozenset(
    {
        ResourceKind.FUNCTION,
        ResourceKind.ASGI_SERVICE,
        ResourceKind.SCHEDULE,
        ResourceKind.JOB,
    }
)

_TEMPLATE_OUTPUTS: tuple[tuple[str, str], ...] = (
    ("Dockerfile.j2", "Dockerfile"),
    ("handler.py.j2", "handler.py"),
    ("bootstrap.py.j2", "bootstrap.py"),
    ("pyproject.toml.j2", "pyproject.toml"),
)


def build_artefacts(
    bound: Plan,
    env: Environment,
    app_spec: AppSpec,
    *,
    out_dir: Path | None = None,
    requirements: Iterable[str] | None = None,
    python_version: str = "3.11",
    dev: bool = False,
) -> Path:
    """Render every deploy artefact `bound` needs into ``out_dir``.

    Args:
        bound: The bound plan to render. Resources whose backend does not
            need a build artefact (e.g. `Sqlite`, `DynamoDB`) are skipped.
        env: The active environment. ``env.target`` picks the template
            subdirectory.
        app_spec: The parsed ``module:attribute`` reference for the live
            `App`. ``app_spec.top_package`` is the directory the
            Dockerfile copies into the build context; ``app_spec.reference``
            is the import string the generated `bootstrap.py` uses.
        out_dir: Destination directory. Defaults to
            ``./.skaal/build/<env.name>``.
        requirements: Extra ``[project].dependencies`` rendered into
            ``pyproject.toml``. Defaults to a Skaal extra set derived
            from the target resource kinds — for example,
            ``("skaal[runtime,aws]",)`` for plain Lambda functions and
            ``("skaal[runtime,aws,fastapi]",)`` for mounted ASGI apps.
        python_version: Python minor version embedded in the Dockerfile
            base image and the rendered ``requires-python`` marker.

    Returns:
        The directory the artefacts were written to (the resolved
        ``out_dir``).

    Raises:
        BuildError: If the env target is not supported, or no
            Lambda-shaped resources are present.
        MissingExtraError: If the templating dependency (`jinja2`) is not
            installed.
    """
    if env.target not in (Target.AWS, Target.GCP):
        raise BuildError(
            f"`skaal build` supports targets {Target.AWS.value!r} and "
            f"{Target.GCP.value!r}; env {env.name!r} targets {env.target.value!r}."
        )

    template_env = _Jinja2(_template_root(env.target))
    resolved_out = (out_dir or Path(".skaal") / "build" / env.name).resolve()
    resolved_out.mkdir(parents=True, exist_ok=True)

    target_resources = tuple(_lambda_resources(bound.resources))
    if not target_resources:
        raise BuildError(
            "No Lambda-shaped resources to build. Add at least one "
            "`@app.function`, `@app.schedule`, `@app.job`, or `app.mount(...)` "
            "to the app."
        )

    resolved_requirements: tuple[str, ...] = (
        tuple(requirements)
        if requirements is not None
        else _default_requirements(env.target, target_resources)
    )
    if dev:
        resolved_requirements = _rewrite_requirements_for_dev(resolved_requirements)

    runtime_bindings = RuntimeBindingManifest.from_bound_plan(bound, env)
    runtime_bindings_json = runtime_bindings.to_json()
    (resolved_out / "runtime_bindings.json").write_text(runtime_bindings_json, encoding="utf-8")

    user_package_source = _resolve_user_package_dir(app_spec.top_package)
    skaal_source_root = _resolve_skaal_source_root() if dev else None

    entries: list[ManifestResourceEntry] = []
    for resource in target_resources:
        slug = resource_slug(resource)
        resource_dir = resolved_out / slug
        resource_dir.mkdir(parents=True, exist_ok=True)
        context = BuildContext(
            app_name=bound.app,
            env_name=env.name,
            target=env.target,
            user_package=app_spec.top_package,
            app_target=app_spec.reference,
            python_version=python_version,
            resource_id=resource.inferred.id,
            resource_kind=resource.inferred.kind,
            resource_bare_name=resource.inferred.source.bare_name,
            backend=resource.backend,
            bound_fingerprint=bound.bound_fingerprint,
            app_fingerprint=bound.app_fingerprint,
            requirements=resolved_requirements,
            dev_skaal_source=dev,
        )
        _render_resource(template_env, context, resource_dir)
        (resource_dir / "runtime_bindings.json").write_text(
            runtime_bindings_json,
            encoding="utf-8",
        )
        if user_package_source is not None:
            _copy_user_package(user_package_source, resource_dir / app_spec.top_package)
        if skaal_source_root is not None:
            _copy_skaal_source(skaal_source_root, resource_dir / "_skaal_src")
        entries.append(ManifestResourceEntry.for_resource(resource, slug=slug))

    manifest = BuildManifest(
        app=bound.app,
        environment=env.name,
        target=env.target,
        app_fingerprint=bound.app_fingerprint,
        bound_fingerprint=bound.bound_fingerprint,
        resources=tuple(entries),
    )
    (resolved_out / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")

    return resolved_out


def _render_resource(template_env: _Jinja2, context: BuildContext, resource_dir: Path) -> None:
    """Render each template in `_TEMPLATE_OUTPUTS` into ``resource_dir``."""
    render_kwargs: dict[str, Any] = context.model_dump(mode="json")
    for template_name, output_name in _TEMPLATE_OUTPUTS:
        rendered = template_env.get_template(template_name).render(**render_kwargs)
        (resource_dir / output_name).write_text(rendered, encoding="utf-8")


def _resolve_user_package_dir(top_package: str) -> Path | None:
    """Locate the user's source package directory on disk.

    The Dockerfile renders a ``COPY <top_package> ./<top_package>`` line; the
    Docker build context is the per-Lambda artefact directory, so the build
    must mirror the user's package source into each artefact directory before
    `pulumi up` invokes Docker.

    Synthetic test `AppSpec`s may reference a package that is not importable in
    the current process. In that case we still render the artefacts and let the
    later Docker build fail if the source tree is genuinely missing.
    """
    try:
        spec = find_spec(top_package)
    except (ImportError, ValueError):
        return None
    if spec is None:
        return None
    locations = list(spec.submodule_search_locations or ())
    if locations:
        return Path(locations[0]).resolve()
    if spec.origin and spec.origin != "built-in":
        return Path(spec.origin).resolve().parent
    return None


def _copy_user_package(source: Path, dest: Path) -> None:
    """Mirror ``source`` into ``dest``, dropping caches.

    Idempotent: removes any prior copy first so stale `.pyc` files from a
    previous build do not bleed into the new image layer.
    """
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        source,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".mypy_cache", ".ruff_cache"),
    )


def _resolve_skaal_source_root() -> Path:
    """Locate the repo root that holds `skaal/` + `pyproject.toml`.

    `--dev` mode ships the local Skaal source tree inside each Lambda image
    so the unreleased alpha can be exercised without a TestPyPI publish.
    """
    skaal_spec = find_spec("skaal")
    locations = list(skaal_spec.submodule_search_locations or ()) if skaal_spec else []
    if not locations:
        raise BuildError(
            "`--dev` mode could not locate the local `skaal` package source. "
            "Run `skaal build --dev` from a checkout that has `skaal/` importable."
        )
    skaal_dir = Path(locations[0]).resolve()
    repo_root = skaal_dir.parent
    if not (repo_root / "pyproject.toml").exists():
        raise BuildError(
            f"`--dev` mode found `skaal/` at {skaal_dir} but no sibling "
            "`pyproject.toml`. The local checkout must contain both."
        )
    return repo_root


def _copy_skaal_source(repo_root: Path, dest: Path) -> None:
    """Mirror the local Skaal checkout (`skaal/` + `pyproject.toml`) into ``dest``."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copytree(
        repo_root / "skaal",
        dest / "skaal",
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".mypy_cache", ".ruff_cache", "tests"
        ),
    )
    shutil.copy2(repo_root / "pyproject.toml", dest / "pyproject.toml")
    for sibling in ("README.md", "LICENSE", "CITATION.cff"):
        candidate = repo_root / sibling
        if candidate.exists():
            shutil.copy2(candidate, dest / sibling)


def _rewrite_requirements_for_dev(requirements: tuple[str, ...]) -> tuple[str, ...]:
    """Repoint any `skaal[...]` requirement at the in-image `_skaal_src/` path.

    Without this rewrite, `uv pip install -r pyproject.toml` resolves
    `skaal[runtime,aws]` from PyPI — which only has the published `0.3.x`
    line and pulls in deleted dependencies (`z3-solver` etc.). The dev
    build copies the local checkout to `_skaal_src/` inside the image; the
    PEP 508 direct reference below installs from that path instead.
    """
    rewritten: list[str] = []
    for spec in requirements:
        stripped = spec.strip()
        if stripped == "skaal" or stripped.startswith(("skaal[", "skaal ")):
            rewritten.append(f"{stripped} @ file:///var/task/_skaal_src")
        else:
            rewritten.append(stripped)
    return tuple(rewritten)


def _lambda_resources(resources_in: Iterable[PlannedResource]) -> Iterable[PlannedResource]:
    """Yield the resources that need per-Lambda artefacts.

    Externals are skipped (their connections come from
    `Environment.backends[...]` at runtime); storage / channel / secret
    resources do not get their own Lambda image.
    """
    for resource in resources_in:
        if resource.external:
            continue
        if resource.inferred.kind in _LAMBDA_KINDS:
            yield resource


def _slug_for(resource: PlannedResource) -> str:
    """Return a filesystem-safe slug for a bound resource.

    Combines the typed `SourceLocation.bare_name` with a short hash of
    the full id so two same-named resources in different modules do not
    collide on disk.
    """
    return resource_slug(resource)


def _default_requirements(
    target: Target, resources: Iterable[PlannedResource] = ()
) -> tuple[str, ...]:
    """Default `[project].dependencies` for the rendered `pyproject.toml`.

    Returns only `skaal[...]` extras — every transitive third-party
    dependency (mangum for ASGI-on-Lambda, asyncpg for Postgres,
    google-cloud-* for GCP clients, …) is pulled in through skaal's
    optional-dependency table in ``pyproject.toml``. Pinning bare
    package names here would split the dependency source-of-truth.
    """
    extras = ["runtime", target.value]
    if any(resource.inferred.kind is ResourceKind.ASGI_SERVICE for resource in resources):
        extras.append("fastapi")
    return (f"skaal[{','.join(extras)}]",)


def _template_root(target: Target) -> Path:
    """Resolve the on-disk Jinja2 template directory for ``target``.

    Templates ship in the wheel under ``skaal/deploy/templates/<target>``;
    ``importlib.resources`` returns a `Path` traversable for both
    development checkouts and installed wheels.
    """
    with resources.as_file(resources.files("skaal.deploy.templates") / target.value) as path:
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
    """Thin wrapper around `jinja2.Environment` that surfaces a clean error."""

    def __init__(self, template_root: Path) -> None:
        try:
            from jinja2 import Environment, FileSystemLoader, StrictUndefined
        except ImportError as exc:  # pragma: no cover - exercised in CI matrix
            raise MissingExtraError(
                "`skaal build` requires jinja2. Install it via the `skaal[deploy]` extra."
            ) from exc
        # Autoescape is intentionally disabled: the templates render
        # Dockerfiles, Python source, and TOML — not HTML. Escaping would
        # corrupt the output (e.g. mangling `>=` in a dep constraint).
        # Template inputs are fully framework-controlled (the
        # `BuildContext` pydantic model); no user-supplied request data
        # flows through this rendering path.
        self._env: Any = Environment(  # nosec B701
            loader=FileSystemLoader(str(template_root)),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )

    def get_template(self, name: str) -> Any:
        return self._env.get_template(name)


__all__ = ["build_artefacts"]
