"""Tests for `skaal.deploy.build_artefacts`."""

from __future__ import annotations

from pathlib import Path

import pytest

from skaal import App, Store
from skaal.binding.model import Environment, LockFile, Target
from skaal.deploy import AppSpec, BuildManifest, build_artefacts
from skaal.errors import BuildError
from skaal.inference.model import ResourceKind


def _bound_for(app: App, *, env: Environment | None = None):
    env = env or Environment(name="prod", target=Target.AWS, region="us-east-1")
    return app.plan(env, lock=LockFile()), env


def _spec_for(app: App) -> AppSpec:
    return AppSpec.for_app(app)


def _read_manifest(out_dir: Path) -> BuildManifest:
    return BuildManifest.model_validate_json(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )


def test_build_artefacts_writes_dockerfile_handler_bootstrap_pyproject(
    tmp_path: Path,
) -> None:
    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_for(app)
    out = build_artefacts(bound, env, _spec_for(app), out_dir=tmp_path)

    subdirs = [p for p in out.iterdir() if p.is_dir()]
    assert len(subdirs) == 1
    resource_dir = subdirs[0]

    for name in ("Dockerfile", "handler.py", "bootstrap.py", "pyproject.toml"):
        rendered = resource_dir / name
        assert rendered.exists(), f"missing {name}"
        body = rendered.read_text(encoding="utf-8")
        assert body, f"{name} is empty"

    dockerfile = (resource_dir / "Dockerfile").read_text(encoding="utf-8")
    assert "python:3.11" in dockerfile
    assert "uv pip install" in dockerfile
    assert "SKAAL_APP=svc" in dockerfile


def test_build_artefacts_round_trips_manifest_through_pydantic(tmp_path: Path) -> None:
    app = App("svc")

    @app.expose()
    async def predict(x: int) -> int:
        return x + 1

    bound, env = _bound_for(app)
    out = build_artefacts(bound, env, _spec_for(app), out_dir=tmp_path)

    manifest = _read_manifest(out)
    assert manifest.app == "svc"
    assert manifest.environment == "prod"
    assert manifest.target is Target.AWS
    assert manifest.bound_fingerprint == bound.bound_fingerprint
    assert manifest.app_fingerprint == bound.app_fingerprint
    assert len(manifest.resources) == 1
    entry = manifest.resources[0]
    assert entry.kind is ResourceKind.FUNCTION
    assert "predict" in entry.id
    assert entry.external is False
    assert entry.slug.startswith("predict-")


def test_build_artefacts_skips_storage_resources(tmp_path: Path) -> None:
    """Stores (DynamoDB, sqlite, ...) do not get a Lambda artefact tree."""
    app = App("svc")

    @app.storage()
    class Cache(Store[dict]):
        pass

    @app.expose()
    async def hit(key: str) -> dict:
        return await Cache.get(key) or {}

    bound, env = _bound_for(app)
    out = build_artefacts(bound, env, _spec_for(app), out_dir=tmp_path)

    subdirs = [p for p in out.iterdir() if p.is_dir()]
    assert len(subdirs) == 1
    manifest = _read_manifest(out)
    assert {entry.kind for entry in manifest.resources} == {ResourceKind.FUNCTION}


def test_build_artefacts_rejects_non_aws_target(tmp_path: Path) -> None:
    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    env = Environment(name="local", target=Target.LOCAL)
    bound, _ = _bound_for(app, env=env)

    with pytest.raises(BuildError, match="supports targets 'aws' and 'gcp'"):
        build_artefacts(bound, env, _spec_for(app), out_dir=tmp_path)


def test_build_artefacts_rejects_empty_app(tmp_path: Path) -> None:
    app = App("svc")
    bound, env = _bound_for(app)
    with pytest.raises(BuildError, match="No Lambda-shaped resources"):
        build_artefacts(bound, env, _spec_for(app), out_dir=tmp_path)


def test_build_artefacts_renders_dependencies_into_pyproject(tmp_path: Path) -> None:
    """Custom `requirements` flow into `[project].dependencies` in `pyproject.toml`."""
    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_for(app)
    out = build_artefacts(
        bound,
        env,
        _spec_for(app),
        out_dir=tmp_path,
        requirements=["skaal[runtime,aws]", "skaal[secrets-aws]"],
    )
    resource_dir = next(p for p in out.iterdir() if p.is_dir())
    pyproject = (resource_dir / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project]" in pyproject
    assert "skaal[runtime,aws]" in pyproject
    assert "skaal[secrets-aws]" in pyproject
    assert 'requires-python = ">=3.11"' in pyproject


def test_build_artefacts_default_requirements_use_only_skaal_extras(
    tmp_path: Path,
) -> None:
    """No bare third-party deps appear in the default `pyproject.toml`."""
    import tomllib

    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_for(app)
    out = build_artefacts(bound, env, _spec_for(app), out_dir=tmp_path)
    resource_dir = next(p for p in out.iterdir() if p.is_dir())
    pyproject = tomllib.loads((resource_dir / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["dependencies"] == ["skaal[runtime,aws]"]
    assert pyproject["project"]["requires-python"] == ">=3.11"


def test_build_artefacts_renders_app_target_into_bootstrap(tmp_path: Path) -> None:
    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_for(app)
    out = build_artefacts(
        bound,
        env,
        AppSpec(module="examples.todo_api", attribute="app"),
        out_dir=tmp_path,
    )
    resource_dir = next(p for p in out.iterdir() if p.is_dir())
    bootstrap = (resource_dir / "bootstrap.py").read_text(encoding="utf-8")
    assert "examples.todo_api:app" in bootstrap


def test_build_artefacts_uses_default_out_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defaults the build output to `./.skaal/build/<env_name>` under cwd."""
    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_for(app)
    monkeypatch.chdir(tmp_path)
    out = build_artefacts(bound, env, _spec_for(app))

    assert out == (tmp_path / ".skaal" / "build" / env.name).resolve()
    assert (tmp_path / ".skaal" / "build" / env.name).is_dir()


def test_build_artefacts_resource_slug_is_filesystem_safe(tmp_path: Path) -> None:
    """Slugs strip module dots and add a short hash to disambiguate."""
    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_for(app)
    out = build_artefacts(bound, env, _spec_for(app), out_dir=tmp_path)
    subdirs = [p.name for p in out.iterdir() if p.is_dir()]
    slug = subdirs[0]
    assert slug.startswith("greet-")
    suffix = slug.rsplit("-", 1)[-1]
    assert len(suffix) == 8
    assert all(c in "0123456789abcdef" for c in suffix)


def test_build_artefacts_uses_app_spec_top_package_in_dockerfile(
    tmp_path: Path,
) -> None:
    """`COPY {{ user_package }}` uses the parsed top package, not a re-split string."""
    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_for(app)
    spec = AppSpec(module="my_corp.payments.api", attribute="app")
    out = build_artefacts(bound, env, spec, out_dir=tmp_path)
    resource_dir = next(p for p in out.iterdir() if p.is_dir())
    dockerfile = (resource_dir / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY my_corp" in dockerfile
