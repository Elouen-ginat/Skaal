"""Thin loader for the canonical FastAPI todo example.

The on-disk package directory is `examples/02_todo_api/` — the leading
digit makes it un-importable as a dotted name, so this module loads
`app.py` via `importlib.util.spec_from_file_location` and re-exports
the result. The loaded module is registered in `sys.modules` so
pydantic's forward-reference resolver can find nested models declared
inside it.
"""

from __future__ import annotations

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_LOADED_NAME = "examples._todo_api_impl"
_MODULE_PATH = Path(__file__).with_name("02_todo_api") / "app.py"
_SPEC = spec_from_file_location(_LOADED_NAME, _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Could not load example module from {_MODULE_PATH}")

_MODULE = module_from_spec(_SPEC)
sys.modules[_LOADED_NAME] = _MODULE
_SPEC.loader.exec_module(_MODULE)

app = _MODULE.app
api = _MODULE.api

__all__ = ["api", "app"]
