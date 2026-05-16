"""TOML loader for `skaal.toml` → `dict[str, Environment]` (ADR 031 §3.6).

`skaal.toml` is a new file the redesign introduces; it carries the
per-environment binding state (target, region, overrides, per-backend
config). The legacy ``[tool.skaal]`` section in `pyproject.toml` keeps
ownership of the CLI verb flags (`SKAAL_*` env vars, default target/
region) via `skaal.settings.SkaalSettings`; the two coexist until Phase 4
retires the legacy CLI surface.

When `skaal.toml` is absent, `load_environments` returns a single baseline
``Environment(name="local", target=Target.LOCAL)`` so ``skaal run`` works
out of the box.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from skaal.binding.model import BackendConfig, Environment, ResourceOverride, Target
from skaal.errors import SkaalConfigError

SKAAL_TOML = "skaal.toml"


def _find_skaal_toml(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` (or cwd) looking for `skaal.toml`."""
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / SKAAL_TOML
        if candidate.exists():
            return candidate
    return None


def load_environments(path: Path | None = None) -> dict[str, Environment]:
    """Load every `[env.<name>]` block from `skaal.toml`.

    Args:
        path: Explicit path to a TOML file, or `None` to search upward from cwd.

    Returns:
        A mapping from env name to `Environment`. When no file is found,
        returns a single baseline ``{"local": Environment(name="local",
        target=LOCAL)}``.

    Raises:
        SkaalConfigError: The TOML is malformed or any `[env.<name>]` block
            has an unknown key or an invalid target.
    """
    resolved = path or _find_skaal_toml()
    if resolved is None or not resolved.exists():
        return {"local": Environment(name="local", target=Target.LOCAL)}
    try:
        with resolved.open("rb") as fh:
            raw = tomllib.load(fh)
    except OSError as exc:
        msg = f"cannot read {resolved}: {exc}"
        raise SkaalConfigError(msg) from exc
    except tomllib.TOMLDecodeError as exc:
        msg = f"{resolved} is not valid TOML: {exc}"
        raise SkaalConfigError(msg) from exc

    env_section = raw.get("env", {})
    if not isinstance(env_section, dict):
        msg = f"{resolved}: top-level 'env' must be a table"
        raise SkaalConfigError(msg)

    sections = cast(dict[str, Any], env_section)
    result: dict[str, Environment] = {}
    for raw_name, block in sections.items():
        name = str(raw_name)
        if not isinstance(block, dict):
            msg = f"{resolved}: [env.{name}] must be a table"
            raise SkaalConfigError(msg)
        result[name] = _build_environment(name, cast(dict[str, Any], block), resolved)
    return result


def load_environment(name: str, path: Path | None = None) -> Environment:
    """Load a single `[env.<name>]` block; raises if it is missing."""
    envs = load_environments(path)
    if name not in envs:
        valid = ", ".join(sorted(envs)) or "(none)"
        msg = f"environment {name!r} not found in skaal.toml. Defined: {valid}"
        raise SkaalConfigError(msg)
    return envs[name]


def _build_environment(name: str, block: dict[str, Any], source: Path) -> Environment:
    target_raw = block.get("target")
    if not isinstance(target_raw, str):
        msg = f"{source}: [env.{name}] requires a string 'target' (local|aws|gcp)"
        raise SkaalConfigError(msg)
    try:
        target = Target(target_raw)
    except ValueError as exc:
        valid = ", ".join(t.value for t in Target)
        msg = f"{source}: [env.{name}].target = {target_raw!r} (expected one of: {valid})"
        raise SkaalConfigError(msg) from exc

    overrides_raw: Any = block.get("overrides") or {}
    if not isinstance(overrides_raw, dict):
        msg = f"{source}: [env.{name}.overrides] must be a table"
        raise SkaalConfigError(msg)
    overrides_section = cast(dict[str, Any], overrides_raw)
    overrides: dict[str, ResourceOverride] = {
        str(res_id): _build_override(name, str(res_id), value, source)
        for res_id, value in overrides_section.items()
    }

    backends_raw: Any = block.get("backends") or {}
    if not isinstance(backends_raw, dict):
        msg = f"{source}: [env.{name}.backends] must be a table"
        raise SkaalConfigError(msg)
    backends_section = cast(dict[str, Any], backends_raw)
    backends: dict[str, BackendConfig] = {
        str(backend_name): _build_backend_config(name, str(backend_name), value, source)
        for backend_name, value in backends_section.items()
    }

    region_value = block.get("region")
    region: str | None = region_value if isinstance(region_value, str) else None

    try:
        return Environment(
            name=name,
            target=target,
            region=region,
            overrides=overrides,
            backends=backends,
        )
    except ValidationError as exc:
        msg = f"{source}: [env.{name}] failed validation: {exc.errors()}"
        raise SkaalConfigError(msg) from exc


def _build_override(env_name: str, res_id: str, value: Any, source: Path) -> ResourceOverride:
    if isinstance(value, str):
        return ResourceOverride(backend=value)
    if isinstance(value, dict):
        payload = cast(dict[str, Any], value)
        try:
            return ResourceOverride(**payload)
        except ValidationError as exc:
            msg = (
                f"{source}: [env.{env_name}.overrides] entry {res_id!r} "
                f"failed validation: {exc.errors()}"
            )
            raise SkaalConfigError(msg) from exc
    msg = (
        f"{source}: [env.{env_name}.overrides] entry {res_id!r} must be a "
        f"string backend name or an inline table"
    )
    raise SkaalConfigError(msg)


def _build_backend_config(
    env_name: str, backend_name: str, value: Any, source: Path
) -> BackendConfig:
    if not isinstance(value, dict):
        msg = f"{source}: [env.{env_name}.backends.{backend_name}] must be a table"
        raise SkaalConfigError(msg)
    section = cast(dict[str, Any], value)
    known = {"region", "project", "dataset", "emulator", "table_prefix"}
    payload: dict[str, Any] = {str(k): v for k, v in section.items() if k in known}
    extra: dict[str, Any] = {str(k): v for k, v in section.items() if k not in known}
    if extra:
        payload["options"] = extra
    try:
        return BackendConfig(**payload)
    except ValidationError as exc:
        msg = (
            f"{source}: [env.{env_name}.backends.{backend_name}] failed validation: {exc.errors()}"
        )
        raise SkaalConfigError(msg) from exc
