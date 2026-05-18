"""Tests for lazy imports in `skaal.runtime`."""

from __future__ import annotations

import importlib
import sys


def test_runtime_models_import_does_not_eagerly_import_local_runtime() -> None:
    sys.modules.pop("skaal.runtime", None)
    sys.modules.pop("skaal.runtime.local", None)
    sys.modules.pop("skaal.runtime.models", None)

    importlib.import_module("skaal.runtime.models")

    assert "skaal.runtime.local" not in sys.modules
