"""Tests for `skaal.binding.lock` TOML reader/writer."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from skaal.binding.lock import load_lock, write_lock
from skaal.binding.model import LockEntry, LockFile


def test_absent_file_returns_empty_lock(tmp_path: Path) -> None:
    lock = load_lock(tmp_path / "missing.lock")
    assert lock == LockFile()


def test_write_then_load_round_trips(tmp_path: Path) -> None:
    entry = LockEntry(
        backend="dynamodb",
        region="eu-west-1",
        pinned_at=datetime(2026, 5, 12, 14, 0, 0, tzinfo=UTC),
        pinned_by="alice@acme.com",
        fingerprint="abc123",
    )
    original = LockFile(
        version=1,
        entries={
            ("prod", "acme.users:Users"): entry,
            ("prod", "acme.users:Avatars"): LockEntry(
                backend="s3",
                pinned_at=datetime(2026, 5, 12, 14, 0, 0, tzinfo=UTC),
            ),
        },
    )
    path = tmp_path / "skaal.lock"
    write_lock(path, original)
    reloaded = load_lock(path)
    assert reloaded.version == original.version
    assert reloaded.entries == original.entries


def test_load_handles_multiple_environments(tmp_path: Path) -> None:
    path = tmp_path / "skaal.lock"
    path.write_text(
        """
version = 1

[entries.dev."acme.users:Users"]
backend = "sqlite"
pinned_at = "2026-05-12T14:00:00+00:00"

[entries.prod."acme.users:Users"]
backend = "dynamodb"
pinned_at = "2026-05-12T14:00:00+00:00"
""".strip()
    )
    lock = load_lock(path)
    assert lock.entries[("dev", "acme.users:Users")].backend == "sqlite"
    assert lock.entries[("prod", "acme.users:Users")].backend == "dynamodb"
