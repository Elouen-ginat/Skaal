"""Project-level lock file for multi-app Skaal projects.

`plan.skaal.project.lock` records the apps in the project, their deploy
order, the cross-app dependency edges, and the last-deployed URL per app
so that a partial deploy (`skaal deploy frontend`) can read upstream URLs
without re-deploying the whole graph.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

PROJECT_LOCK_FILE_NAME = "plan.skaal.project.lock"
PROJECT_LOCK_VERSION = 1


@dataclass
class ProjectLockEntry:
    """One app's recorded state in the project lock file."""

    module: str
    target: str
    depends_on: list[str] = field(default_factory=list)
    last_deploy: str | None = None
    last_url: str | None = None
    plan_lock: str | None = None


@dataclass
class ProjectLock:
    """Full contents of `plan.skaal.project.lock`."""

    apps: dict[str, ProjectLockEntry] = field(default_factory=dict)
    updated_at: str | None = None
    version: int = PROJECT_LOCK_VERSION

    @classmethod
    def read(cls, path: Path | str = PROJECT_LOCK_FILE_NAME) -> ProjectLock:
        """Read a project lock file, or return an empty one if absent."""
        target = Path(path)
        if not target.exists():
            return cls()
        with target.open("rb") as fh:
            data = tomllib.load(fh)
        apps: dict[str, ProjectLockEntry] = {}
        for name, entry in (data.get("apps") or {}).items():
            apps[name] = ProjectLockEntry(
                module=entry.get("module", ""),
                target=entry.get("target", ""),
                depends_on=list(entry.get("depends_on", [])),
                last_deploy=entry.get("last_deploy"),
                last_url=entry.get("last_url"),
                plan_lock=entry.get("plan_lock"),
            )
        return cls(
            apps=apps,
            updated_at=data.get("updated_at"),
            version=data.get("version", PROJECT_LOCK_VERSION),
        )

    def write(self, path: Path | str = PROJECT_LOCK_FILE_NAME) -> Path:
        """Persist the lock file to disk and return the written path."""
        target = Path(path)
        self.updated_at = datetime.now(UTC).isoformat(timespec="seconds")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render_toml(), encoding="utf-8")
        return target

    def _render_toml(self) -> str:
        """Hand-roll a small TOML document — one [apps.<name>] table per app."""
        lines: list[str] = [
            f"version = {self.version}",
            f'updated_at = "{self.updated_at}"',
        ]
        for name, entry in sorted(self.apps.items()):
            lines.append("")
            lines.append(f"[apps.{name}]")
            lines.append(f'module = "{_escape(entry.module)}"')
            lines.append(f'target = "{_escape(entry.target)}"')
            if entry.depends_on:
                rendered = ", ".join(f'"{_escape(d)}"' for d in entry.depends_on)
                lines.append(f"depends_on = [{rendered}]")
            if entry.last_deploy:
                lines.append(f'last_deploy = "{_escape(entry.last_deploy)}"')
            if entry.last_url:
                lines.append(f'last_url = "{_escape(entry.last_url)}"')
            if entry.plan_lock:
                lines.append(f'plan_lock = "{_escape(entry.plan_lock)}"')
        return "\n".join(lines) + "\n"

    def upsert(
        self,
        name: str,
        *,
        module: str,
        target: str,
        depends_on: list[str] | None = None,
        last_url: str | None = None,
        plan_lock: str | Path | None = None,
    ) -> ProjectLockEntry:
        """Insert-or-update an entry and stamp ``last_deploy`` to now."""
        entry = self.apps.get(name) or ProjectLockEntry(module=module, target=target)
        entry.module = module
        entry.target = target
        if depends_on is not None:
            entry.depends_on = list(depends_on)
        if last_url is not None:
            entry.last_url = last_url
        if plan_lock is not None:
            entry.plan_lock = str(plan_lock)
        entry.last_deploy = datetime.now(UTC).isoformat(timespec="seconds")
        self.apps[name] = entry
        return entry

    def url_for(self, name: str) -> str | None:
        """Return the recorded ``last_url`` for *name*, or ``None``."""
        entry = self.apps.get(name)
        return entry.last_url if entry else None


def _escape(value: str) -> str:
    """Escape a string for embedding in a basic TOML string literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


__all__ = [
    "PROJECT_LOCK_FILE_NAME",
    "PROJECT_LOCK_VERSION",
    "ProjectLock",
    "ProjectLockEntry",
]
