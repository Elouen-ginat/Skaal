"""Unified Skaal configuration loaded from env, dotenv, pyproject, and TOML.

`SkaalSettings` is the single process-wide configuration entry point for the
CLI and Python API. It merges four user-facing surfaces into one structured
pydantic model:

1. `SKAAL_*` environment variables
2. `.skaal.env`
3. `[tool.skaal]` in `pyproject.toml`
4. `skaal.toml`

`pyproject.toml` is the preferred project-level surface. `skaal.toml` remains a
compatibility and environment-definition source during the redesign, and still
supports the familiar `[env.<name>]` blocks.
"""

from __future__ import annotations

import json
import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

from dotenv import dotenv_values
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from skaal.binding.model import BackendConfig, Environment, EnvOverride, Target
from skaal.errors import SkaalConfigError

LogFormat = Literal["text", "json"]
PYPROJECT_TOML = "pyproject.toml"
SKAAL_TOML = "skaal.toml"
SKAAL_ENV_FILE = ".skaal.env"


def _find_upward(filename: str, *, start: Path | None = None) -> Path | None:
    """Walk up from ``start`` (or cwd) until ``filename`` is found."""
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / filename
        if candidate.exists():
            return candidate
    return None


def _read_toml_file(path: Path | None) -> dict[str, Any]:
    """Return parsed TOML content or an empty dict on missing/unreadable files."""
    if path is None or not path.exists():
        return {}
    try:
        with path.open("rb") as fh:
            parsed = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return cast(dict[str, Any], parsed)


def _coerce_env_value(raw: str) -> Any:
    """Best-effort parse for env and dotenv values.

    JSON payloads are decoded so users can pass dict/list values through env
    vars. Bare strings stay as strings.
    """
    value = raw.strip()
    if not value:
        return raw
    if value[0] not in '[{"0123456789-tfn':
        return raw
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return raw


def _set_nested(target: dict[str, Any], path: list[str], value: Any) -> None:
    """Assign ``value`` into ``target`` under a nested ``path``."""
    current = target
    for segment in path[:-1]:
        current = cast(dict[str, Any], current.setdefault(segment, {}))
    current[path[-1]] = value


def _string_key_mapping(raw: Any) -> dict[str, Any]:
    """Return ``raw`` as a ``dict[str, Any]`` when it is mapping-shaped."""
    if not isinstance(raw, dict):
        return {}
    raw_dict = cast(dict[Any, Any], raw)
    return {str(key): value for key, value in raw_dict.items()}


def _normalize_environment_blocks(raw: Any) -> dict[str, Any]:
    """Normalize keyed environment tables into the structured settings shape."""
    result: dict[str, Any] = {}
    for raw_name, raw_block in _string_key_mapping(raw).items():
        if not isinstance(raw_block, dict):
            continue
        result[str(raw_name)] = _string_key_mapping(raw_block)
    return result


def _normalize_pyproject_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Map `[tool.skaal]` into the structured settings model."""
    normalized: dict[str, Any] = {}
    defaults: dict[str, Any] = {}
    paths: dict[str, Any] = {}

    app = raw.get("app")
    if isinstance(app, str):
        defaults["app"] = app

    default_environment = raw.get("default_environment")
    if isinstance(default_environment, str):
        defaults["environment"] = default_environment
    elif isinstance(raw.get("env"), str):
        defaults["environment"] = raw["env"]

    default_target = raw.get("default_target")
    if isinstance(default_target, str):
        defaults["target"] = default_target

    default_region = raw.get("default_region")
    if isinstance(default_region, str):
        defaults["region"] = default_region

    for source_key, target_key in (("toml", "toml"), ("lock", "lock"), ("out", "out")):
        value = raw.get(source_key)
        if isinstance(value, str):
            paths[target_key] = value

    paths_section = _string_key_mapping(raw.get("paths"))
    if paths_section:
        for source_key, target_key in (("toml", "toml"), ("lock", "lock"), ("out", "out")):
            value = paths_section.get(source_key)
            if isinstance(value, str):
                paths[target_key] = value

    run_section = _string_key_mapping(raw.get("run"))
    if run_section:
        normalized["run"] = run_section

    logging_section = _string_key_mapping(raw.get("logging"))
    if logging_section:
        normalized["logging"] = logging_section

    backend_defaults = _string_key_mapping(raw.get("backend_defaults"))
    if backend_defaults:
        normalized["backend_defaults"] = backend_defaults

    environments = _string_key_mapping(raw.get("environments"))
    if environments:
        normalized["environments"] = _normalize_environment_blocks(environments)

    if defaults:
        normalized["defaults"] = defaults
    if paths:
        normalized["paths"] = paths
    return normalized


def _normalize_skaal_toml_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Map `skaal.toml` into the structured settings model."""
    normalized: dict[str, Any] = {}
    defaults = _string_key_mapping(raw.get("defaults"))
    if defaults:
        normalized["defaults"] = defaults

    run = _string_key_mapping(raw.get("run"))
    if run:
        normalized["run"] = run

    logging_section = _string_key_mapping(raw.get("logging"))
    if logging_section:
        normalized["logging"] = logging_section

    backend_defaults = _string_key_mapping(raw.get("backend_defaults"))
    if backend_defaults:
        normalized["backend_defaults"] = backend_defaults

    environments = _string_key_mapping(raw.get("env"))
    if environments:
        normalized["environments"] = _normalize_environment_blocks(environments)
    return normalized


def _normalize_env_mapping(raw: dict[str, str | None]) -> dict[str, Any]:
    """Map `SKAAL_*` env vars or dotenv values into the structured model."""
    normalized: dict[str, Any] = {}
    legacy_fields = {
        "SKAAL_APP": ["defaults", "app"],
        "SKAAL_DEFAULT_ENVIRONMENT": ["defaults", "environment"],
        "SKAAL_DEFAULT_TARGET": ["defaults", "target"],
        "SKAAL_DEFAULT_REGION": ["defaults", "region"],
        "SKAAL_TOML": ["paths", "toml"],
        "SKAAL_LOCK": ["paths", "lock"],
        "SKAAL_OUT": ["paths", "out"],
        "SKAAL_RUN_HOST": ["run", "host"],
        "SKAAL_RUN_PORT": ["run", "port"],
        "SKAAL_LOG_LEVEL": ["logging", "level"],
        "SKAAL_LOG_FORMAT": ["logging", "format"],
        "SKAAL_LOG_LOGGERS": ["logging", "loggers"],
        "SKAAL_ENVIRONMENTS": ["environments"],
        "SKAAL_BACKEND_DEFAULTS": ["backend_defaults"],
    }

    for key, raw_value in raw.items():
        if raw_value is None or not key.startswith("SKAAL_"):
            continue
        if key == "SKAAL_ENV":
            continue
        value = _coerce_env_value(raw_value)
        if key in legacy_fields:
            _set_nested(normalized, legacy_fields[key], value)
            continue
        suffix = key.removeprefix("SKAAL_")
        if "__" not in suffix:
            continue
        path = [segment.lower() for segment in suffix.split("__") if segment]
        if path:
            _set_nested(normalized, path, value)
    return normalized


# ── pyproject.toml discovery ──────────────────────────────────────────────────


def find_pyproject() -> Path | None:
    """Walk up from cwd until a ``pyproject.toml`` is found, or return None."""
    return _find_upward(PYPROJECT_TOML)


def find_skaal_toml() -> Path | None:
    """Walk up from cwd until a ``skaal.toml`` is found, or return None."""
    return _find_upward(SKAAL_TOML)


def load_skaal_section() -> dict[str, Any]:
    """Return the ``[tool.skaal]`` dict from the nearest pyproject.toml, or {}."""
    data = _read_toml_file(find_pyproject())
    tool = _string_key_mapping(data.get("tool"))
    return _string_key_mapping(tool.get("skaal"))


def load_skaal_toml_section(path: Path | None = None) -> dict[str, Any]:
    """Return the raw `skaal.toml` content, or {} when it is absent."""
    if path is None:
        pyproject = load_skaal_section()
        direct_toml = pyproject.get("toml")
        if isinstance(direct_toml, str):
            path = Path(direct_toml)
        else:
            paths = _string_key_mapping(pyproject.get("paths"))
            toml_path = paths.get("toml")
            if isinstance(toml_path, str):
                path = Path(toml_path)
    return _read_toml_file(path or find_skaal_toml())


# ── pydantic-settings custom source ───────────────────────────────────────────


class _StaticMappingSource(PydanticBaseSettingsSource):
    """Base source backed by one precomputed mapping."""

    def __init__(self, settings_cls: type[BaseSettings], data: dict[str, Any]) -> None:
        super().__init__(settings_cls)
        self._data = data

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        value = self._data.get(field_name)
        return value, field_name, False

    def field_is_complex(self, field: Any) -> bool:
        return False

    def __call__(self) -> dict[str, Any]:
        known = set(self.settings_cls.model_fields)
        return {key: value for key, value in self._data.items() if key in known}


class EnvVarSource(_StaticMappingSource):
    """Settings source backed by live `SKAAL_*` environment variables."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls, _normalize_env_mapping(dict(os.environ)))


class DotenvSource(_StaticMappingSource):
    """Settings source backed by the optional `.skaal.env` file."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        path = Path(SKAAL_ENV_FILE)
        data = dotenv_values(path) if path.exists() else {}
        normalized = _normalize_env_mapping({str(key): value for key, value in data.items()})
        super().__init__(settings_cls, normalized)


class PyprojectTomlSource(_StaticMappingSource):
    """pydantic-settings source that reads ``[tool.skaal]`` from pyproject.toml."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls, _normalize_pyproject_config(load_skaal_section()))


class SkaalTomlSource(_StaticMappingSource):
    """pydantic-settings source that reads the compatibility `skaal.toml` file."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls, _normalize_skaal_toml_config(load_skaal_toml_section()))


# ── Logging sub-model ─────────────────────────────────────────────────────────


class LoggingSettings(BaseModel):
    """Structured logging settings shared by the CLI and Python API."""

    level: str | None = None
    format: LogFormat = "text"
    loggers: dict[str, str] = Field(default_factory=dict)


class DefaultsSettings(BaseModel):
    """Project-wide defaults used when a command omits explicit flags."""

    app: str | None = None
    environment: str | None = None
    target: Target | None = None
    region: str | None = None


class PathSettings(BaseModel):
    """Filesystem locations used by the binding and deploy layers."""

    toml: Path = Path(SKAAL_TOML)
    lock: Path = Path("skaal.lock")
    out: Path = Path(".skaal/build")


class RunSettings(BaseModel):
    """Defaults for `skaal run`."""

    host: str = "127.0.0.1"
    port: int = 8000


class EnvironmentSettings(BaseModel):
    """One named environment before defaults are applied."""

    target: Target | None = None
    region: str | None = None
    overrides: dict[str, EnvOverride] = Field(default_factory=dict)
    backends: dict[str, BackendConfig] = Field(default_factory=dict)


# ── Central settings ──────────────────────────────────────────────────────────


class SkaalSettings(BaseSettings):
    """Structured Skaal configuration merged from every supported source."""

    model_config = SettingsConfigDict(
        extra="ignore",
    )

    defaults: DefaultsSettings = Field(default_factory=DefaultsSettings)
    paths: PathSettings = Field(default_factory=PathSettings)
    run: RunSettings = Field(default_factory=RunSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    backend_defaults: dict[str, BackendConfig] = Field(default_factory=dict)
    environments: dict[str, EnvironmentSettings] = Field(default_factory=dict)

    @property
    def default_environment(self) -> str | None:
        """Default named environment used when `--env` is omitted."""
        return self.defaults.environment

    @property
    def default_target(self) -> Target | None:
        """Default target for synthesized environments."""
        return self.defaults.target

    @property
    def default_region(self) -> str | None:
        """Default region for synthesized or partially-defined environments."""
        return self.defaults.region

    @property
    def app(self) -> str | None:
        """Default `module:attribute` app reference, if configured."""
        return self.defaults.app

    @property
    def env(self) -> str | None:
        """Back-compat alias for the default environment name."""
        return self.default_environment

    @property
    def toml(self) -> Path:
        """Back-compat alias for the configured `skaal.toml` path."""
        return self.paths.toml

    @property
    def lock(self) -> Path:
        """Back-compat alias for the configured `skaal.lock` path."""
        return self.paths.lock

    @property
    def out(self) -> Path:
        """Back-compat alias for the configured build output directory."""
        return self.paths.out

    @property
    def resolved_logging(self) -> LoggingSettings:
        """Resolved logging configuration.

        The logging model is already normalised across sources, so the property
        now simply exposes that merged value.
        """
        return self.logging

    def synthesize_environment(self, name: str | None = None) -> Environment:
        """Build one environment from project defaults when none are declared."""
        env_name = name or self.default_environment or "local"
        target = self.default_target or Target.LOCAL
        return Environment(
            name=env_name,
            target=target,
            region=self.default_region,
            backends=self.backend_defaults,
        )

    def materialize_environment(self, name: str, config: EnvironmentSettings) -> Environment:
        """Resolve one configured environment into the binding-layer model."""
        target = config.target or self.default_target
        if target is None:
            msg = (
                f"environment {name!r} has no target. Set `[tool.skaal].default_target`, "
                f"`[defaults].target` in {self.toml.name}, or `target` on that environment."
            )
            raise SkaalConfigError(msg)

        merged_backends: dict[str, BackendConfig] = dict(self.backend_defaults)
        for backend_name, backend in config.backends.items():
            if backend_name in merged_backends:
                merged_backends[backend_name] = _merge_backend_config(
                    merged_backends[backend_name],
                    backend,
                )
                continue
            merged_backends[backend_name] = backend

        return Environment(
            name=name,
            target=target,
            region=config.region or self.default_region,
            overrides=config.overrides,
            backends=merged_backends,
        )

    def list_environments(self) -> dict[str, Environment]:
        """Return all resolved environments known to the current config."""
        if not self.environments:
            baseline = self.synthesize_environment()
            return {baseline.name: baseline}
        return {
            name: self.materialize_environment(name, config)
            for name, config in self.environments.items()
        }

    def require_environment(self, name: str) -> Environment:
        """Return one resolved environment or raise a configuration error."""
        environments = self.list_environments()
        if name not in environments:
            valid = ", ".join(sorted(environments)) or "(none)"
            msg = f"environment {name!r} not found. Defined: {valid}"
            raise SkaalConfigError(msg)
        return environments[name]

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
            EnvVarSource(settings_cls),
            DotenvSource(settings_cls),
            PyprojectTomlSource(settings_cls),
            SkaalTomlSource(settings_cls),
        )


def _merge_backend_config(base: BackendConfig, overlay: BackendConfig) -> BackendConfig:
    """Merge a project-level backend default with one env-specific override."""
    overlay_fields = overlay.model_fields_set
    return BackendConfig(
        region=overlay.region if "region" in overlay_fields else base.region,
        project=overlay.project if "project" in overlay_fields else base.project,
        dataset=overlay.dataset if "dataset" in overlay_fields else base.dataset,
        emulator=overlay.emulator if "emulator" in overlay_fields else base.emulator,
        table_prefix=(
            overlay.table_prefix if "table_prefix" in overlay_fields else base.table_prefix
        ),
        options={**base.options, **overlay.options},
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
    "DefaultsSettings",
    "DotenvSource",
    "EnvVarSource",
    "EnvironmentSettings",
    "LogFormat",
    "LoggingSettings",
    "PathSettings",
    "PyprojectTomlSource",
    "RunSettings",
    "SkaalSettings",
    "find_pyproject",
    "find_skaal_toml",
    "get_settings",
    "load_skaal_section",
    "load_skaal_toml_section",
    "reset_settings_cache",
]
