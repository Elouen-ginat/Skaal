"""Fixtures for relational-migration tests."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def isolated_cwd(tmp_path: Path) -> Iterator[Path]:
    """Run the test inside *tmp_path* so .skaal/migrations/ is per-test."""
    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(previous)
