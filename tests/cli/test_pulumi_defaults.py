"""Tests for `apply_pulumi_defaults` backend-selection heuristics."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from rich.console import Console

from skaal.cli._pulumi import apply_pulumi_defaults


@pytest.fixture
def isolated_pulumi_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Isolate `apply_pulumi_defaults` from the real home dir and CWD."""
    monkeypatch.chdir(tmp_path)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.delenv("PULUMI_BACKEND_URL", raising=False)
    monkeypatch.delenv("PULUMI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("PULUMI_CONFIG_PASSPHRASE", raising=False)
    return tmp_path


def test_picks_local_backend_when_no_login(isolated_pulumi_env: Path) -> None:
    apply_pulumi_defaults(Console(quiet=True))
    assert os.environ["PULUMI_BACKEND_URL"].startswith("file://")
    assert os.environ["PULUMI_CONFIG_PASSPHRASE"] == ""


def test_keeps_cloud_backend_when_login_and_token_present(
    isolated_pulumi_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = Path.home() / ".pulumi" / "credentials.json"
    credentials.parent.mkdir(parents=True, exist_ok=True)
    credentials.write_text('{"current": "https://api.pulumi.com"}', encoding="utf-8")
    monkeypatch.setenv("PULUMI_ACCESS_TOKEN", "pul-fake-token")

    apply_pulumi_defaults(Console(quiet=True))

    # No backend override applied — Pulumi will read credentials.json.
    assert "PULUMI_BACKEND_URL" not in os.environ


def test_falls_back_to_local_when_login_exists_but_token_missing(
    isolated_pulumi_env: Path,
) -> None:
    """A stranded credentials.json (e.g. created by `pulumi/actions@v6` without
    `PULUMI_ACCESS_TOKEN`) must not route us at the cloud backend — otherwise
    `skaal destroy` fails with "PULUMI_ACCESS_TOKEN must be set"."""
    credentials = Path.home() / ".pulumi" / "credentials.json"
    credentials.parent.mkdir(parents=True, exist_ok=True)
    credentials.write_text('{"current": "https://api.pulumi.com"}', encoding="utf-8")

    apply_pulumi_defaults(Console(quiet=True))

    assert os.environ["PULUMI_BACKEND_URL"].startswith("file://")


def test_pins_to_local_when_state_dir_already_exists(
    isolated_pulumi_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If an earlier deploy created `.skaal/pulumi-state/`, destroy must
    stay on the same backend regardless of any cloud setup that appeared in
    between."""
    (isolated_pulumi_env / ".skaal" / "pulumi-state").mkdir(parents=True)
    credentials = Path.home() / ".pulumi" / "credentials.json"
    credentials.parent.mkdir(parents=True, exist_ok=True)
    credentials.write_text('{"current": "https://api.pulumi.com"}', encoding="utf-8")
    monkeypatch.setenv("PULUMI_ACCESS_TOKEN", "pul-fake-token")

    apply_pulumi_defaults(Console(quiet=True))

    assert os.environ["PULUMI_BACKEND_URL"].startswith("file://")


def test_caller_set_backend_wins(
    isolated_pulumi_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PULUMI_BACKEND_URL", "s3://my-state-bucket")

    apply_pulumi_defaults(Console(quiet=True))

    assert os.environ["PULUMI_BACKEND_URL"] == "s3://my-state-bucket"
