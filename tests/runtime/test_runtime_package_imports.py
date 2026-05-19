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
    names_to_reset = [
        name
        for name in list(sys.modules)
        if name in {"skaal", "redis", "pulumi"} or name.startswith(("skaal.", "redis.", "pulumi."))
    ]
    original_modules = {name: sys.modules[name] for name in names_to_reset}

    try:
        for name in names_to_reset:
            sys.modules.pop(name, None)

        importlib.import_module("skaal")

        assert "redis.asyncio.client" not in sys.modules
        assert "pulumi" not in sys.modules
    finally:
        for name in list(sys.modules):
            if name in original_modules:
                sys.modules.pop(name, None)

        sys.modules.update(original_modules)
