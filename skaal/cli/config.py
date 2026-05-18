"""Back-compat re-export of :mod:`skaal.settings`.

The settings live at :mod:`skaal.settings` so the CLI and the
:mod:`skaal.api` Python API share one source of truth. This module
re-exports them for any code still importing from ``skaal.cli.config``.
"""

from __future__ import annotations

from skaal.settings import (
    LoggingSettings,
    PyprojectTomlSource,
    SkaalSettings,
    find_pyproject,
    get_settings,
    load_skaal_section,
)

__all__ = [
    "LoggingSettings",
    "PyprojectTomlSource",
    "SkaalSettings",
    "find_pyproject",
    "get_settings",
    "load_skaal_section",
]
