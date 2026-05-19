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


def test_skaal_import_does_not_eagerly_import_redis_asyncio() -> None:
    for name in list(sys.modules):
        if name == "skaal" or name.startswith("skaal."):
            sys.modules.pop(name, None)
        if name == "redis" or name.startswith("redis."):
            sys.modules.pop(name, None)
        if name == "pulumi" or name.startswith("pulumi."):
            sys.modules.pop(name, None)

    importlib.import_module("skaal")

    assert "redis.asyncio.client" not in sys.modules
    assert "pulumi" not in sys.modules
