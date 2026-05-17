"""Tests for Lambda image tagging from rendered artifact contents."""

from __future__ import annotations

from pathlib import Path

from skaal.deploy.aws._lambda import _artifact_tag_for_dir


def test_artifact_tag_changes_when_rendered_file_changes(tmp_path: Path) -> None:
    resource_dir = tmp_path / "increment-b8ee2273"
    resource_dir.mkdir()
    (resource_dir / "bootstrap.py").write_text("print('old')\n", encoding="utf-8")
    (resource_dir / "handler.py").write_text("print('handler')\n", encoding="utf-8")

    first = _artifact_tag_for_dir(resource_dir)
    (resource_dir / "bootstrap.py").write_text("print('new')\n", encoding="utf-8")
    second = _artifact_tag_for_dir(resource_dir)

    assert first != second


def test_artifact_tag_is_stable_for_same_contents(tmp_path: Path) -> None:
    resource_dir = tmp_path / "increment-b8ee2273"
    resource_dir.mkdir()
    (resource_dir / "bootstrap.py").write_text("print('same')\n", encoding="utf-8")
    (resource_dir / "handler.py").write_text("print('handler')\n", encoding="utf-8")

    first = _artifact_tag_for_dir(resource_dir)
    second = _artifact_tag_for_dir(resource_dir)

    assert first == second
