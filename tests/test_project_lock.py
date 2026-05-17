"""Tests for `plan.skaal.project.lock` reader/writer."""

from __future__ import annotations

from pathlib import Path

from skaal.project_lock import ProjectLock, ProjectLockEntry


def test_roundtrip(tmp_path: Path) -> None:
    lock = ProjectLock()
    lock.upsert(
        "backend",
        module="myproj.backend:app",
        target="gcp",
        last_url="https://backend-abc.run.app",
        plan_lock="artifacts/backend/plan.skaal.lock",
    )
    lock.upsert(
        "frontend",
        module="myproj.frontend:app",
        target="gcp",
        depends_on=["backend"],
        last_url="https://frontend-def.run.app",
    )

    path = tmp_path / "project.lock"
    lock.write(path)
    assert path.exists()

    reloaded = ProjectLock.read(path)
    assert set(reloaded.apps) == {"backend", "frontend"}
    assert reloaded.apps["frontend"].depends_on == ["backend"]
    assert reloaded.apps["backend"].last_url == "https://backend-abc.run.app"
    assert reloaded.apps["backend"].plan_lock == "artifacts/backend/plan.skaal.lock"


def test_read_missing_returns_empty(tmp_path: Path) -> None:
    lock = ProjectLock.read(tmp_path / "does-not-exist.lock")
    assert lock.apps == {}


def test_url_for_unknown_returns_none() -> None:
    lock = ProjectLock(apps={"backend": ProjectLockEntry(module="x", target="gcp")})
    assert lock.url_for("frontend") is None
    assert lock.url_for("backend") is None  # no last_url set


def test_upsert_stamps_last_deploy() -> None:
    lock = ProjectLock()
    entry = lock.upsert("backend", module="x:y", target="gcp")
    assert entry.last_deploy is not None
