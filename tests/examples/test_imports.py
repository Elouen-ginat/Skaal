"""Collection-time import gate for every example under `examples/`.

Each surviving example must expose an `app` symbol of type `skaal.App` reachable
through `from examples.<name> import app`. The Phase 7 sweep dropped the
digit prefixes and the flat loader shims so the package paths are now plain
Python identifiers — this test fails fast if a future change reintroduces a
non-importable layout.
"""

from __future__ import annotations

import importlib

import pytest

from skaal import App

EXAMPLES = [
    "examples.counter",
    "examples.hello_world",
    "examples.todo_api",
    "examples.fastapi_streaming",
    "examples.file_upload_api",
    "examples.session_cache",
    "examples.team_directory",
]


@pytest.mark.parametrize("dotted", EXAMPLES)
def test_example_exposes_app(dotted: str) -> None:
    module = importlib.import_module(dotted)
    app = getattr(module, "app", None)
    assert isinstance(app, App), f"{dotted}.app is not a skaal.App instance: {app!r}"
