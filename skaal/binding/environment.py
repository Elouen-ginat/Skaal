"""Binding-layer environment loading backed by the unified `SkaalSettings`.

The settings module now owns config discovery and precedence across env vars,
`.skaal.env`, `pyproject.toml`, and `skaal.toml`. This module stays as the
binding-layer entry point so callers can keep importing from
`skaal.binding.environment`, but the actual source of truth is the structured
`SkaalSettings` model.
"""

from __future__ import annotations

from pathlib import Path

from skaal.binding.model import Environment
from skaal.settings import SkaalSettings, load_settings


def load_environments(path: Path | None = None) -> SkaalSettings:
    """Load the structured Skaal configuration for binding operations.

    Args:
        path: Explicit `skaal.toml` path, or `None` to use normal discovery.

    Returns:
        The fully merged `SkaalSettings` model.
    """
    return load_settings(toml_path=path)


def load_environment(name: str, path: Path | None = None) -> Environment:
    """Load one resolved environment by name."""
    return load_environments(path).require_environment(name)
