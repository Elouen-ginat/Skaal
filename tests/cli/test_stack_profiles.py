"""Tests for per-stack settings profiles."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from skaal.settings import SkaalSettings, StackProfile


def _write_pyproject(tmp_path: Path, body: str) -> None:
    (tmp_path / "pyproject.toml").write_text(dedent(body))


def test_no_profile_returns_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """for_stack() on an unknown name returns a copy with only `stack` updated."""
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal]
        target = "gcp"
        region = "europe-west1"
        gcp_project = "base-proj"
        """,
    )
    monkeypatch.chdir(tmp_path)

    resolved = SkaalSettings().for_stack("nonexistent")
    assert resolved.stack == "nonexistent"
    assert resolved.region == "europe-west1"
    assert resolved.gcp_project == "base-proj"


def test_profile_overrides_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fields on the profile win; unset fields fall through to the base."""
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal]
        target = "gcp"
        region = "europe-west1"

        [tool.skaal.stacks.p-prd]
        gcp_project = "my-prd-proj"
        region      = "europe-west4"

        [tool.skaal.stacks.p-dev]
        gcp_project = "my-dev-proj"
        """,
    )
    monkeypatch.chdir(tmp_path)

    base = SkaalSettings()
    assert base.gcp_project is None
    assert set(base.stacks) == {"p-prd", "p-dev"}

    prd = base.for_stack("p-prd")
    assert prd.stack == "p-prd"
    assert prd.gcp_project == "my-prd-proj"
    assert prd.region == "europe-west4"

    dev = base.for_stack("p-dev")
    assert dev.stack == "p-dev"
    assert dev.gcp_project == "my-dev-proj"
    assert dev.region == "europe-west1"  # fell through


def test_for_stack_none_uses_current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """for_stack(None) resolves the currently-selected stack."""
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal]
        stack  = "p-ppr"
        target = "gcp"

        [tool.skaal.stacks.p-ppr]
        gcp_project = "my-ppr-proj"
        """,
    )
    monkeypatch.chdir(tmp_path)

    resolved = SkaalSettings().for_stack(None)
    assert resolved.stack == "p-ppr"
    assert resolved.gcp_project == "my-ppr-proj"


def test_unknown_profile_field_rejected() -> None:
    """Typos in profile keys are caught, not silently dropped."""
    with pytest.raises(ValueError):
        StackProfile.model_validate({"regionn": "oops"})


def test_env_var_beats_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SKAAL_* env vars live on the base settings and survive for_stack()
    when the profile does not override that field."""
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal]
        target = "gcp"

        [tool.skaal.stacks.p-dev]
        gcp_project = "from-profile"
        """,
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKAAL_REGION", "from-env")

    resolved = SkaalSettings().for_stack("p-dev")
    assert resolved.region == "from-env"
    assert resolved.gcp_project == "from-profile"
