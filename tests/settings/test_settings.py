"""Tests for the unified Skaal settings model and source precedence."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from skaal.binding.environment import load_environments
from skaal.binding.model import Target


def test_pyproject_only_configuration_materializes_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [tool.skaal]
            app = "examples.counter_api:app"
            default_target = "aws"
            default_environment = "prod"

            [tool.skaal.environments.prod]
            region = "eu-west-1"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_environments()
    env = config.require_environment("prod")

    assert config.app == "examples.counter_api:app"
    assert env.target is Target.AWS
    assert env.region == "eu-west-1"


def test_pyproject_configuration_overrides_skaal_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [tool.skaal]
            default_target = "gcp"

            [tool.skaal.environments.prod]
            region = "europe-west1"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "skaal.toml").write_text(
        textwrap.dedent(
            """
            [defaults]
            target = "aws"

            [env.prod]
            region = "us-east-1"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    env = load_environments().require_environment("prod")

    assert env.target is Target.GCP
    assert env.region == "europe-west1"


def test_environment_variables_override_pyproject(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [tool.skaal]
            default_target = "gcp"
            default_environment = "prod"
            app = "examples.counter_api:app"

            [tool.skaal.environments.prod]
            region = "europe-west1"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKAAL_DEFAULT_TARGET", "aws")
    monkeypatch.setenv("SKAAL_DEFAULT_ENVIRONMENT", "staging")
    monkeypatch.setenv("SKAAL_APP", "examples.hello_world:app")
    monkeypatch.setenv("SKAAL_ENVIRONMENTS__staging__region", "us-east-1")

    config = load_environments()
    env = config.require_environment("staging")

    assert config.app == "examples.hello_world:app"
    assert config.default_environment == "staging"
    assert env.target is Target.AWS
    assert env.region == "us-east-1"


def test_default_target_synthesizes_baseline_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [tool.skaal]
            default_target = "gcp"
            default_environment = "sandbox"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    envs = load_environments().list_environments()

    assert sorted(envs) == ["sandbox"]
    assert envs["sandbox"].target is Target.GCP
