"""Tests for `skaal.deploy.program.pulumi_program_for`.

The closure builder itself works without pulumi installed; only invoking
the closure requires the optional extras. These tests cover both halves.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skaal import App
from skaal.binding.model import Environment, LockFile, Target
from skaal.deploy import pulumi_program_for
from skaal.errors import MissingExtraError


def _bound_aws(app: App) -> tuple:
    env = Environment(name="prod", target=Target.AWS, region="us-east-1")
    return app.plan(env, lock=LockFile()), env


def test_pulumi_program_for_returns_callable_without_pulumi(tmp_path: Path) -> None:
    """The closure builder must not require pulumi to be importable."""
    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_aws(app)
    program = pulumi_program_for(bound, env, tmp_path)
    assert callable(program)


def test_program_invocation_unregistered_target_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When no target package can be imported, the closure raises clean."""
    import builtins

    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_aws(app)
    program = pulumi_program_for(bound, env, tmp_path)

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "skaal.deploy.aws" or name.startswith("pulumi"):
            raise ImportError(f"blocked: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(MissingExtraError, match="skaal\\[deploy,aws\\]"):
        program()


def test_program_invocation_extras_missing_raises_missing_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the target imports but pulumi SDKs are missing, the closure raises."""
    import builtins

    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    bound, env = _bound_aws(app)
    # Force-import the target so it self-registers before we block pulumi.
    pytest.importorskip("pulumi_aws")
    import skaal.deploy.aws  # noqa: F401 — side effect

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


def test_pulumi_program_for_gcp_target_resolves(
    tmp_path: Path,
) -> None:
    """GCP now has a registered deploy package (ADR 042); the program builds."""
    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    env = Environment(name="gcp-prod", target=Target.GCP, region="us-central1")
    bound = app.plan(env, lock=LockFile())
    # `pulumi_program_for` returns a callable; we don't invoke it (that requires
    # a running event loop / Pulumi stack), but the build path must succeed.
    program = pulumi_program_for(bound, env, tmp_path)
    assert callable(program)
