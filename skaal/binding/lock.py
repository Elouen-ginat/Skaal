"""TOML reader/writer for `skaal.lock` (ADR 028 §6.10, ADR 031 §3.7).

`skaal.lock` is machine-written by ``skaal deploy``. On-disk it is a TOML
file with the nested form ``[entries.<env>."<resource_id>"]``; in memory
it is a `LockFile` whose `entries` is keyed by ``(env_name, resource_id)``.
This module is the only place that translates between the two.
"""

from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from skaal.binding.model import LockEntry, LockFile
from skaal.errors import SkaalConfigError


def load_lock(path: Path) -> LockFile:
    """Load `skaal.lock` from disk, or return an empty `LockFile` if absent."""
    if not path.exists():
        return LockFile()
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except OSError as exc:
        msg = f"cannot read {path}: {exc}"
        raise SkaalConfigError(msg) from exc
    except tomllib.TOMLDecodeError as exc:
        msg = f"{path} is not valid TOML: {exc}"
        raise SkaalConfigError(msg) from exc

    version = raw.get("version", 1)
    if not isinstance(version, int):
        msg = f"{path}: 'version' must be an integer"
        raise SkaalConfigError(msg)

    entries_section: Any = raw.get("entries") or {}
    if not isinstance(entries_section, dict):
        msg = f"{path}: 'entries' must be a table"
        raise SkaalConfigError(msg)

    sections = cast(dict[str, Any], entries_section)
    entries: dict[tuple[str, str], LockEntry] = {}
    for env_name_raw, per_env in sections.items():
        env_name = str(env_name_raw)
        if not isinstance(per_env, dict):
            msg = f"{path}: [entries.{env_name}] must be a table"
            raise SkaalConfigError(msg)
        per_env_section = cast(dict[str, Any], per_env)
        for resource_id_raw, entry_data in per_env_section.items():
            resource_id = str(resource_id_raw)
            if not isinstance(entry_data, dict):
                msg = f"{path}: [entries.{env_name}.{resource_id!r}] must be a table"
                raise SkaalConfigError(msg)
            try:
                entries[(env_name, resource_id)] = LockEntry(**cast(dict[str, Any], entry_data))
            except ValidationError as exc:
                msg = (
                    f"{path}: [entries.{env_name}.{resource_id!r}] failed "
                    f"validation: {exc.errors()}"
                )
                raise SkaalConfigError(msg) from exc

    return LockFile(version=version, entries=entries)


def write_lock(path: Path, lock: LockFile) -> None:
    """Write a `LockFile` to disk in the nested TOML form."""
    lines: list[str] = [f"version = {lock.version}", ""]
    grouped: dict[str, dict[str, LockEntry]] = {}
    for (env_name, resource_id), entry in lock.entries.items():
        grouped.setdefault(env_name, {})[resource_id] = entry

    for env_name in sorted(grouped):
        per_env = grouped[env_name]
        for resource_id in sorted(per_env):
            entry = per_env[resource_id]
            lines.append(f'[entries.{env_name}."{resource_id}"]')
            for key, value in _render_entry(entry).items():
                lines.append(f"{key} = {value}")
            lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _render_entry(entry: LockEntry) -> dict[str, str]:
    payload: dict[str, Any] = entry.model_dump(mode="json")
    rendered: dict[str, str] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, str):
            rendered[key] = _quote(value)
        elif isinstance(value, bool):
            rendered[key] = "true" if value else "false"
        elif isinstance(value, datetime):
            rendered[key] = _quote(value.isoformat())
        else:
            rendered[key] = repr(value)
    return rendered


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
