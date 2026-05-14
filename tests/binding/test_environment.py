"""Tests for `skaal.binding.environment` TOML loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from skaal.binding.environment import load_environment, load_environments
from skaal.binding.model import Target
from skaal.errors import SkaalConfigError


def test_missing_file_returns_local_baseline(tmp_path: Path) -> None:
    envs = load_environments(tmp_path / "missing.toml")
    assert set(envs) == {"local"}
    assert envs["local"].target == Target.LOCAL


def test_load_minimal_env(tmp_path: Path) -> None:
    path = tmp_path / "skaal.toml"
    path.write_text(
        """
[env.prod]
target = "aws"
region = "eu-west-1"
""".strip()
    )
    envs = load_environments(path)
    assert envs["prod"].target == Target.AWS
    assert envs["prod"].region == "eu-west-1"


def test_load_env_with_overrides_and_backends(tmp_path: Path) -> None:
    path = tmp_path / "skaal.toml"
    path.write_text(
        """
[env.prod]
target = "aws"

[env.prod.overrides]
"acme.users:Users"   = "dynamodb"
"acme.users:Avatars" = { backend = "s3", region = "us-east-1" }

[env.prod.backends.dynamodb]
region = "eu-west-1"
table_prefix = "acme-"

[env.prod.backends.bigquery]
project = "acme-prod"
dataset = "warehouse"
""".strip()
    )
    env = load_environment("prod", path)
    assert env.overrides["acme.users:Users"].backend == "dynamodb"
    assert env.overrides["acme.users:Avatars"].backend == "s3"
    assert env.overrides["acme.users:Avatars"].region == "us-east-1"
    assert env.backends["dynamodb"].region == "eu-west-1"
    assert env.backends["dynamodb"].table_prefix == "acme-"
    assert env.backends["bigquery"].project == "acme-prod"
    assert env.backends["bigquery"].dataset == "warehouse"


def test_invalid_target_raises(tmp_path: Path) -> None:
    path = tmp_path / "skaal.toml"
    path.write_text(
        """
[env.prod]
target = "azure"
""".strip()
    )
    with pytest.raises(SkaalConfigError):
        load_environments(path)


def test_missing_target_raises(tmp_path: Path) -> None:
    path = tmp_path / "skaal.toml"
    path.write_text(
        """
[env.prod]
region = "eu-west-1"
""".strip()
    )
    with pytest.raises(SkaalConfigError):
        load_environments(path)


def test_load_environment_raises_when_name_missing(tmp_path: Path) -> None:
    path = tmp_path / "skaal.toml"
    path.write_text(
        """
[env.dev]
target = "aws"
""".strip()
    )
    with pytest.raises(SkaalConfigError):
        load_environment("prod", path)


def test_malformed_toml_raises(tmp_path: Path) -> None:
    path = tmp_path / "skaal.toml"
    path.write_text("not = valid = toml")
    with pytest.raises(SkaalConfigError):
        load_environments(path)
