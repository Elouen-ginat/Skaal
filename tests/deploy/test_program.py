"""Tests for `skaal.deploy.program.pulumi_program_for`.

The closure builder itself works without pulumi installed; only invoking
the closure requires the optional extras. These tests cover both halves.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skaal import App
from skaal.binding import bind
from skaal.binding.model import Environment, LockFile, Target
from skaal.deploy import pulumi_program_for
from skaal.errors import MissingExtraError, SkaalDeployError


def _bound_aws(app: App) -> tuple:
    env = Environment(name="prod", target=Target.AWS, region="us-east-1")
    return bind(app.infer(), env, LockFile()), env


def test_pulumi_program_for_rejects_local_target(tmp_path: Path) -> None:
    app = App("svc")

    @app.function()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    env = Environment(name="local", target=Target.LOCAL)
    bound = bind(app.infer(), env, LockFile())
    with pytest.raises(SkaalDeployError, match="only wired for target 'aws'"):
        pulumi_program_for(bound, env, tmp_path)


def test_pulumi_program_for_rejects_gcp_target(tmp_path: Path) -> None:
    app = App("svc")

    @app.function()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    env = Environment(name="gcp-prod", target=Target.GCP, region="us-central1")
    bound = bind(app.infer(), env, LockFile())
    with pytest.raises(SkaalDeployError, match="only wired for target 'aws'"):
        pulumi_program_for(bound, env, tmp_path)


def test_pulumi_program_for_returns_callable_without_pulumi(tmp_path: Path) -> None:
    """The closure builder must not require pulumi to be importable."""
    app = App("svc")

    @app.function()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_aws(app)
    program = pulumi_program_for(bound, env, tmp_path)
    assert callable(program)


def test_program_invocation_without_pulumi_raises_missing_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calling the closure without `pulumi` raises a clean `MissingExtraError`."""
    import builtins

    app = App("svc")

    @app.function()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_aws(app)
    program = pulumi_program_for(bound, env, tmp_path)

    real_import = builtins.__import__
    blocked = {"pulumi", "pulumi_aws", "pulumi_docker"}

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name in blocked:
            raise ImportError(f"blocked: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(MissingExtraError, match="skaal\\[deploy,aws\\]"):
        program()
