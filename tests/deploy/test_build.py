"""Tests for `skaal.deploy.build_artefacts`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skaal import App, Store
from skaal.binding import bind
from skaal.binding.model import Environment, LockFile, Target
from skaal.deploy import build_artefacts
from skaal.errors import BuildError


def _bound_for(app: App, *, env: Environment | None = None):
    env = env or Environment(name="prod", target=Target.AWS, region="us-east-1")
    return bind(app.infer(), env, LockFile()), env


def test_build_artefacts_writes_dockerfile_handler_bootstrap_requirements(
    tmp_path: Path,
) -> None:
    app = App("svc")

    @app.function()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_for(app)
    out = build_artefacts(bound, app, env, out_dir=tmp_path)

    # One directory per non-external Lambda-shaped resource.
    subdirs = [p for p in out.iterdir() if p.is_dir()]
    assert len(subdirs) == 1
    resource_dir = subdirs[0]

    for name in ("Dockerfile", "handler.py", "bootstrap.py", "requirements.txt"):
        rendered = resource_dir / name
        assert rendered.exists(), f"missing {name}"
        body = rendered.read_text(encoding="utf-8")
        assert body, f"{name} is empty"

    dockerfile = (resource_dir / "Dockerfile").read_text(encoding="utf-8")
    assert "python:3.11" in dockerfile
    assert "SKAAL_APP=svc" in dockerfile


def test_build_artefacts_emits_manifest_with_resource_ids(tmp_path: Path) -> None:
    app = App("svc")

    @app.function()
    async def predict(x: int) -> int:
        return x + 1

    bound, env = _bound_for(app)
    out = build_artefacts(bound, app, env, out_dir=tmp_path)

    manifest_path = out / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["app"] == "svc"
    assert manifest["environment"] == "prod"
    assert manifest["target"] == "aws"
    assert manifest["bound_fingerprint"] == bound.bound_fingerprint
    assert len(manifest["resources"]) == 1
    entry = manifest["resources"][0]
    assert entry["kind"] == "function"
    assert "predict" in entry["id"]
    assert entry["external"] is False


def test_build_artefacts_skips_storage_resources(tmp_path: Path) -> None:
    """Stores (DynamoDB, sqlite, ...) do not get a Lambda artefact tree."""
    app = App("svc")

    @app.storage()
    class Cache(Store[dict]):
        pass

    @app.function()
    async def hit(key: str) -> dict:
        return await Cache.get(key) or {}

    bound, env = _bound_for(app)
    out = build_artefacts(bound, app, env, out_dir=tmp_path)

    subdirs = sorted(p.name for p in out.iterdir() if p.is_dir())
    # Cache (STORE → DynamoDB on AWS) does not get an artefact dir; only
    # the FUNCTION does.
    assert len(subdirs) == 1
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert {r["kind"] for r in manifest["resources"]} == {"function"}


def test_build_artefacts_rejects_non_aws_target(tmp_path: Path) -> None:
    app = App("svc")

    @app.function()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    env = Environment(name="local", target=Target.LOCAL)
    bound, _ = _bound_for(app, env=env)

    with pytest.raises(BuildError, match="only supports target 'aws'"):
        build_artefacts(bound, app, env, out_dir=tmp_path)


def test_build_artefacts_rejects_empty_app(tmp_path: Path) -> None:
    app = App("svc")
    bound, env = _bound_for(app)
    with pytest.raises(BuildError, match="No Lambda-shaped resources"):
        build_artefacts(bound, app, env, out_dir=tmp_path)


def test_build_artefacts_renders_requirements_lines(tmp_path: Path) -> None:
    app = App("svc")

    @app.function()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_for(app)
    out = build_artefacts(
        bound,
        app,
        env,
        out_dir=tmp_path,
        requirements=["my-package==1.2.3", "another>=4.5"],
    )
    resource_dir = next(p for p in out.iterdir() if p.is_dir())
    req = (resource_dir / "requirements.txt").read_text(encoding="utf-8")
    assert "my-package==1.2.3" in req
    assert "another>=4.5" in req


def test_build_artefacts_renders_app_target_into_bootstrap(tmp_path: Path) -> None:
    app = App("svc")

    @app.function()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_for(app)
    out = build_artefacts(
        bound,
        app,
        env,
        out_dir=tmp_path,
        app_target="examples.todo_api:app",
    )
    resource_dir = next(p for p in out.iterdir() if p.is_dir())
    bootstrap = (resource_dir / "bootstrap.py").read_text(encoding="utf-8")
    assert "examples.todo_api:app" in bootstrap


def test_build_artefacts_uses_default_out_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defaults the build output to `./.skaal/build/<env_name>` under cwd."""
    app = App("svc")

    @app.function()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_for(app)
    monkeypatch.chdir(tmp_path)
    out = build_artefacts(bound, app, env)

    assert out == Path(".skaal") / "build" / env.name
    assert (tmp_path / ".skaal" / "build" / env.name).is_dir()


def test_build_artefacts_resource_slug_is_filesystem_safe(tmp_path: Path) -> None:
    """Slugs strip module dots and add a short hash to disambiguate."""
    app = App("svc")

    @app.function()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_for(app)
    out = build_artefacts(bound, app, env, out_dir=tmp_path)
    subdirs = [p.name for p in out.iterdir() if p.is_dir()]
    slug = subdirs[0]
    # Slug starts with the bare function name and ends with an 8-hex hash.
    assert slug.startswith("greet-")
    suffix = slug.rsplit("-", 1)[-1]
    assert len(suffix) == 8
    assert all(c in "0123456789abcdef" for c in suffix)
