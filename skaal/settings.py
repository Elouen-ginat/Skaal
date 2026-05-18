"""Unified settings used by the Skaal CLI and Python API.

Per-environment infrastructure config (target, region, backends, overrides)
lives in `skaal.toml` and is loaded into a `skaal.binding.model.Environment`
by `skaal.binding.environment.load_environment`. This module owns the
*cross-environment* knobs instead — default paths, logging, and the default
``--env`` name used when a CLI verb is invoked without ``-e``.

Priority (highest to lowest):
  1. Keyword arguments passed at call time (or CLI flags)
  2. ``SKAAL_*`` environment variables
  3. ``.skaal.env`` file (optional)
  4. ``[tool.skaal]`` section in the nearest ``pyproject.toml``
  5. Built-in defaults

Example ``pyproject.toml``::

    [tool.skaal]
    env  = "staging"      # default --env for verbs that don't set their own
    toml = "skaal.toml"
    lock = "skaal.lock"
    out  = ".skaal/build"

    [tool.skaal.logging]
    level   = "INFO"
    format  = "text"      # text | json
    loggers = { "skaal.deploy" = "DEBUG" }
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

LogFormat = Literal["text", "json"]


# ── pyproject.toml discovery ──────────────────────────────────────────────────


def find_pyproject() -> Path | None:
    """Walk up from cwd until a ``pyproject.toml`` is found, or return None."""
    for directory in [Path.cwd(), *Path.cwd().parents]:
        candidate = directory / "pyproject.toml"
        if candidate.exists():
            return candidate
    return None


def load_skaal_section() -> dict[str, Any]:
    """Return the ``[tool.skaal]`` dict from the nearest pyproject.toml, or {}."""
    path = find_pyproject()
    if path is None:
        return {}
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data.get("tool", {}).get("skaal", {})


# ── pydantic-settings custom source ───────────────────────────────────────────


class PyprojectTomlSource(PydanticBaseSettingsSource):
    """pydantic-settings source that reads ``[tool.skaal]`` from pyproject.toml."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._data: dict[str, Any] = load_skaal_section()

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        value = self._data.get(field_name)
        return value, field_name, False

    def field_is_complex(self, field: Any) -> bool:
        return False

    def __call__(self) -> dict[str, Any]:
        known = set(self.settings_cls.model_fields)
        return {k: v for k, v in self._data.items() if k in known}


# ── Logging sub-model ─────────────────────────────────────────────────────────


class LoggingSettings(BaseModel):
    """``[tool.skaal.logging]`` sub-section.

    `SkaalSettings` exposes the same fields flattened with the ``log_*`` prefix
    for ergonomics on the env-var surface (``SKAAL_LOG_LEVEL`` etc.); this
    nested model exists so `[tool.skaal.logging]` in pyproject.toml stays
    tidy.
    """

    level: str | None = None
    format: LogFormat = "text"
    loggers: dict[str, str] = Field(default_factory=dict)


# ── Central settings ──────────────────────────────────────────────────────────


class SkaalSettings(BaseSettings):
    """Cross-environment Skaal configuration.

    All fields are optional; a default applies when nothing else resolves.
    CLI flags always win over what this class produces; this is the source of
    truth only when the caller did not pass an explicit value.
    """

    model_config = SettingsConfigDict(
        env_prefix="SKAAL_",
        env_file=".skaal.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Paths / defaults consumed by CLI verbs ────────────────────────────────
    env: str | None = Field(
        default=None,
        description=(
            "Default environment name used by CLI verbs that accept ``--env``. "
            "When unset, each verb falls back to its own built-in default."
        ),
    )
    toml: Path = Field(
        default=Path("skaal.toml"),
        description="Path to the `skaal.toml` carrying ``[env.<name>]`` blocks.",
    )
    lock: Path = Field(
        default=Path("skaal.lock"),
        description="Path to the pin-on-first-deploy lock file.",
    )
    out: Path = Field(
        default=Path(".skaal/build"),
        description="Output directory for rendered build artefacts.",
    )

    # ── Logging (flattened for env-var ergonomics) ────────────────────────────
    log_level: str | None = None
    log_format: LogFormat | None = None
    log_loggers: dict[str, str] = Field(default_factory=dict)

    # ── Nested form pulled from [tool.skaal.logging] ──────────────────────────
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    @property
    def resolved_logging(self) -> LoggingSettings:
        """Logging config with flat ``log_*`` overrides applied on top."""
        return LoggingSettings(
            level=self.log_level or self.logging.level,
            format=self.log_format if self.log_format is not None else self.logging.format,
            loggers={**self.logging.loggers, **self.log_loggers},
        )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            PyprojectTomlSource(settings_cls),
        )


@lru_cache(maxsize=1)
def get_settings() -> SkaalSettings:
    """Return the process-wide `SkaalSettings`, evaluating env/pyproject once.

    The result is cached so repeated reads are cheap. Tests that mutate env
    vars must call :func:`reset_settings_cache` to force a re-read.
    """
    return SkaalSettings()


def reset_settings_cache() -> None:
    """Drop the cached `SkaalSettings` instance (use in tests after env edits)."""
    get_settings.cache_clear()


__all__ = [
    "LogFormat",
    "LoggingSettings",
    "PyprojectTomlSource",
    "SkaalSettings",
    "find_pyproject",
    "get_settings",
    "load_skaal_section",
    "reset_settings_cache",
]
