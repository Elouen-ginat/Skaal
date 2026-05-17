"""Tests for `runtime_bindings.json` emission during `skaal build`."""

from __future__ import annotations

from pathlib import Path

from skaal import App, Store
from skaal.binding.model import Environment, LockFile, Target
from skaal.deploy import AppSpec, build_artefacts
from skaal.runtime.models import RuntimeBindingManifest


def _bound_for(app: App, *, env: Environment | None = None):
    env = env or Environment(name="prod", target=Target.AWS, region="us-east-1")
    return app.plan(env, lock=LockFile()), env


def test_build_artefacts_emits_runtime_bindings_next_to_manifest(tmp_path: Path) -> None:
    app = App("svc")

    @app.storage()
    class Cache(Store[dict]):
        pass

    @app.expose()
    async def hit(key: str) -> dict:
        return await Cache.get(key) or {}

    bound, env = _bound_for(app)
    out_dir = build_artefacts(bound, env, AppSpec.for_app(app), out_dir=tmp_path)

    top_level = RuntimeBindingManifest.model_validate_json(
        (out_dir / "runtime_bindings.json").read_text(encoding="utf-8")
    )
    assert top_level.app == "svc"
    assert top_level.environment == "prod"
    assert top_level.target is Target.AWS
    assert len(top_level.bindings) == 1

    resource_dir = next(path for path in out_dir.iterdir() if path.is_dir())
    per_lambda = RuntimeBindingManifest.model_validate_json(
        (resource_dir / "runtime_bindings.json").read_text(encoding="utf-8")
    )
    assert per_lambda == top_level
    dockerfile = (resource_dir / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY bootstrap.py handler.py runtime_bindings.json ./" in dockerfile
    bootstrap = (resource_dir / "bootstrap.py").read_text(encoding="utf-8")
    assert "wire_app_from_environment" in bootstrap
    assert "runtime_bindings.json" in bootstrap


def test_runtime_bindings_emit_store_env_var_keys(tmp_path: Path) -> None:
    app = App("svc")

    @app.storage()
    class Counts(Store[int]):
        pass

    @app.expose()
    async def increment(name: str) -> dict[str, int]:
        value = await Counts.get(name) or 0
        await Counts.set(name, value + 1)
        return {"value": value + 1}

    bound, env = _bound_for(app)
    out_dir = build_artefacts(bound, env, AppSpec.for_app(app), out_dir=tmp_path)

    manifest = RuntimeBindingManifest.model_validate_json(
        (out_dir / "runtime_bindings.json").read_text(encoding="utf-8")
    )
    [binding] = manifest.bindings
    assert binding.resource_id.endswith("Counts")
    assert binding.connection.backend_name == "dynamodb"
    [env_key] = binding.connection.env_var_keys
    assert env_key.startswith("SKAAL_TABLE_COUNTS_")
